"""End-to-end chat pipeline tests, driven through the service with a mock provider."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from nova.chat.service import LOCAL_MODEL, ChatService
from nova.config.settings import Settings
from nova.memory import ChatStore, Database, UsageStore
from nova.providers.base import ToolCall
from nova.providers.errors import AuthError
from nova.providers.mock import MockProvider
from nova.providers.pricing import builtin_table
from nova.security.policy import PolicyEngine
from nova.tools.demo import demo_registry


def build(tmp_path, *, provider=None, settings=None) -> SimpleNamespace:
    database = Database(tmp_path / "memory.db")
    store = ChatStore(database)
    usage = UsageStore(database)
    active = settings or Settings()
    active.provider.name = "mock"
    holder = {"provider": provider or MockProvider(reply="ok")}

    service = ChatService(
        settings=lambda: active,
        provider=lambda: holder["provider"],
        store=store,
        usage=usage,
        registry=demo_registry(),
        policy=PolicyEngine(active.security),
        price_table=builtin_table(),
    )
    return SimpleNamespace(
        service=service,
        store=store,
        usage=usage,
        settings=active,
        holder=holder,
        db=database,
    )


async def collect(service: ChatService, text: str, cid=None, **kwargs):
    events: list[dict] = []

    async def emit(event: dict) -> None:
        events.append(event)

    outcome = await service.handle(text, conversation_id=cid, emit=emit, **kwargs)
    return events, outcome


# -- happy path ------------------------------------------------------------


async def test_streams_and_records_usage(tmp_path):
    env = build(tmp_path, provider=MockProvider(reply="Hello there."))

    events, outcome = await collect(env.service, "explain dictionaries please")

    kinds = [event["type"] for event in events]
    assert kinds[0] == "chat.user"
    for expected in ("chat.start", "chat.delta", "chat.usage", "chat.done"):
        assert expected in kinds
    assert outcome.text == "Hello there."
    assert env.usage.totals().requests_today == 1
    # The free tier is free of charge, so the default tier records $0.
    assert env.usage.totals().today_usd == 0.0


async def test_usage_event_carries_tokens_and_budget(tmp_path):
    env = build(tmp_path, provider=MockProvider(reply="one two three"))

    events, _ = await collect(env.service, "explain dictionaries please")

    usage_event = next(event for event in events if event["type"] == "chat.usage")
    assert usage_event["data"]["output_tokens"] > 0
    assert usage_event["data"]["cost_known"] is True
    assert "budget" in usage_event["data"]


async def test_paid_tier_records_a_cost(tmp_path):
    settings = Settings()
    settings.pricing.tier = "paid"
    env = build(tmp_path, provider=MockProvider(reply="one two three"), settings=settings)

    events, _ = await collect(env.service, "explain dictionaries please")

    usage_event = next(event for event in events if event["type"] == "chat.usage")
    assert usage_event["data"]["cost_usd"] is not None
    assert env.usage.totals().today_usd > 0


# -- local intents ---------------------------------------------------------


async def test_local_intent_never_calls_the_provider(tmp_path):
    env = build(tmp_path, provider=MockProvider(fail_with=AuthError("must not be called")))

    events, outcome = await collect(env.service, "what time is it?")

    assert outcome.model == LOCAL_MODEL
    start = next(event for event in events if event["type"] == "chat.start")
    assert start["data"]["tier"] == "local"
    # No API call, so nothing is charged.
    assert env.usage.totals().requests_today == 0


# -- routing ---------------------------------------------------------------


async def test_strong_model_is_chosen_for_coding(tmp_path):
    env = build(tmp_path)

    events, _ = await collect(env.service, "refactor this function")

    start = next(event for event in events if event["type"] == "chat.start")
    assert start["data"]["tier"] == "strong"
    assert start["data"]["model"] == env.settings.models.strong


async def test_routing_override_forces_fast(tmp_path):
    env = build(tmp_path)

    events, _ = await collect(env.service, "refactor this function", model_override="fast")

    start = next(event for event in events if event["type"] == "chat.start")
    assert start["data"]["tier"] == "fast"
    assert start["data"]["model"] == env.settings.models.fast


# -- tools -----------------------------------------------------------------


async def test_tool_call_is_executed_and_reported(tmp_path):
    provider = MockProvider(reply="Checking the clock.", tool_calls=[ToolCall("get_time", {})])
    env = build(tmp_path, provider=provider)

    events, _ = await collect(env.service, "what is the wall clock reading right now please")

    tools = [event for event in events if event["type"] == "chat.tool"]
    assert tools
    assert tools[0]["data"]["name"] == "get_time"
    assert tools[0]["data"]["status"] == "ok"
    assert tools[0]["data"]["detail"]
    assert tools[0]["data"]["ms"] >= 0


async def test_invalid_tool_arguments_are_blocked(tmp_path):
    provider = MockProvider(reply="ok", tool_calls=[ToolCall("echo", {"text": "hi", "extra": 1})])
    env = build(tmp_path, provider=provider)

    events, _ = await collect(env.service, "please echo something back to me right now")

    tool = next(event for event in events if event["type"] == "chat.tool")
    assert tool["data"]["status"] == "invalid"


async def test_tools_can_be_disabled(tmp_path):
    settings = Settings()
    settings.provider.name = "mock"
    settings.provider.tools_enabled = False
    provider = MockProvider(reply="ok", tool_calls=[ToolCall("get_time", {})])
    env = build(tmp_path, provider=provider, settings=settings)

    events, _ = await collect(env.service, "what is the wall clock reading right now please")

    assert not [event for event in events if event["type"] == "chat.tool"]


# -- budget ----------------------------------------------------------------


async def test_budget_block_prevents_the_call(tmp_path):
    env = build(tmp_path, provider=MockProvider(fail_with=AuthError("must not be called")))
    env.usage.record(model="m", tokens_in=0, tokens_out=0, cost_usd=5.0, tier="paid")
    env.settings.limits.daily_usd = 1.0
    env.settings.limits.hard_stop = True

    events, outcome = await collect(env.service, "explain something entirely unrelated")

    errors = [event for event in events if event["type"] == "chat.error"]
    assert errors and errors[0]["data"]["kind"] == "budget"
    assert outcome.error_kind == "budget"


# -- errors ----------------------------------------------------------------


async def test_provider_error_is_reported_not_raised(tmp_path):
    env = build(tmp_path, provider=MockProvider(fail_with=AuthError("nope")))

    events, outcome = await collect(env.service, "explain something entirely unrelated")

    errors = [event for event in events if event["type"] == "chat.error"]
    assert errors and errors[0]["data"]["kind"] == "auth"
    assert outcome.error_kind == "auth"


# -- cancellation ----------------------------------------------------------


async def test_cancellation_persists_the_partial_reply(tmp_path):
    provider = MockProvider(reply="one two three four five six seven eight nine ten", delay=0.05)
    env = build(tmp_path, provider=provider)

    events: list[dict] = []
    started = asyncio.Event()

    async def emit(event: dict) -> None:
        events.append(event)
        if event["type"] == "chat.delta":
            started.set()

    task = asyncio.create_task(
        env.service.handle("explain something entirely unrelated", conversation_id=None, emit=emit)
    )
    await asyncio.wait_for(started.wait(), timeout=5)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    conversations = env.store.list_conversations()
    messages = env.store.recent_messages(conversations[0]["id"], 20)
    assert any(message.role == "model" and message.content for message in messages)


# -- history and context ---------------------------------------------------


async def test_history_is_reused_across_turns(tmp_path):
    env = build(tmp_path, provider=MockProvider(reply="first"))
    _, first = await collect(env.service, "explain something entirely unrelated")

    env.holder["provider"] = MockProvider(reply="second")
    _, second = await collect(
        env.service, "explain another thing entirely", cid=first.conversation_id
    )

    assert second.conversation_id == first.conversation_id
    assert env.store.count_messages(first.conversation_id) == 4


async def test_context_is_summarized_when_it_grows(tmp_path):
    settings = Settings()
    settings.provider.name = "mock"
    settings.provider.context_window_messages = 4
    settings.provider.summarize_after_messages = 6
    env = build(tmp_path, provider=MockProvider(reply="ok"), settings=settings)

    cid = None
    for index in range(8):
        _, outcome = await collect(env.service, f"explain topic number {index} in detail", cid=cid)
        cid = outcome.conversation_id

    summary, upto = env.store.get_summary(cid)
    assert summary is not None
    assert upto > 0
