"""The chat pipeline: intents, routing, streaming, tools, budget and storage.

Emits UI events through an injected ``emit`` coroutine, so the whole pipeline is
unit-testable without a WebSocket.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from nova.budget import BudgetGuard
from nova.chat.context import Context, ContextBuilder
from nova.config.settings import Settings
from nova.intents import LocalIntent, match_local_intent
from nova.logging_setup import get_logger
from nova.memory.chats import ChatStore
from nova.memory.usage import UsageStore
from nova.providers.base import LLMProvider, LLMRequest, Message, ToolCall, Usage
from nova.providers.errors import ProviderError, SafetyBlockError
from nova.providers.pricing import PriceTable, estimate_cost
from nova.providers.routing import RoutingDecision, RoutingMode, choose_model
from nova.security.policy import PolicyEngine
from nova.tools.executor import ToolExecutor
from nova.tools.registry import ToolRegistry

Emit = Callable[[dict[str, Any]], Awaitable[None]]

MAX_TOOL_ROUNDS = 3
LOCAL_MODEL = "local"

SYSTEM_INSTRUCTION = (
    "You are NOVA, a concise, practical desktop assistant running locally on the user's "
    "Windows machine. Answer the question directly. Use markdown, with fenced code blocks "
    "for code. Never claim to have performed an action you did not perform. If a tool "
    "result is provided, use it rather than guessing."
)

_stream_ids = itertools.count(1)


@dataclass
class ChatOutcome:
    conversation_id: str
    model: str = ""
    text: str = ""
    aborted: bool = False
    error_kind: str | None = None


class ChatService:
    """Turns a user message into streamed UI events and a stored transcript."""

    def __init__(
        self,
        *,
        settings: Callable[[], Settings],
        provider: Callable[[], LLMProvider],
        store: ChatStore,
        usage: UsageStore,
        registry: ToolRegistry,
        policy: PolicyEngine,
        price_table: PriceTable,
    ) -> None:
        self._settings = settings
        self._provider = provider
        self._store = store
        self._usage = usage
        self._registry = registry
        self._policy = policy
        self._price_table = price_table
        self._executor = ToolExecutor(registry, policy)
        self._log = get_logger("chat")

    # -- entry point -------------------------------------------------------
    async def handle(
        self,
        text: str,
        *,
        conversation_id: str | None,
        emit: Emit,
        model_override: str | None = None,
    ) -> ChatOutcome:
        settings = self._settings()
        cid = self._store.ensure_conversation(conversation_id)
        if self._store.count_messages(cid) == 0:
            self._store.set_title(cid, text.strip()[:60] or "New chat")

        self._store.add_message(cid, "user", text)
        await emit({"type": "chat.user", "data": {"text": text, "conversation_id": cid}})

        outcome = ChatOutcome(conversation_id=cid)

        intent = match_local_intent(text)
        if intent is not None:
            return await self._answer_locally(cid, intent, emit, outcome)

        budget = BudgetGuard(self._usage, settings.limits).status()
        if not budget.allowed:
            reason = f"Blocked: {budget.reason}. Raise the limit in Settings."
            self._store.add_message(cid, "model", reason, error_kind="budget")
            await emit({"type": "chat.error", "data": {"kind": "budget", "message": reason}})
            outcome.error_kind = "budget"
            return outcome

        decision = self._resolve(text, settings, model_override)
        outcome.model = decision.model
        stream_id = f"m{next(_stream_ids)}"
        await emit(
            {
                "type": "chat.start",
                "data": {
                    "id": stream_id,
                    "model": decision.model,
                    "tier": decision.tier,
                    "reason": decision.reason,
                    "conversation_id": cid,
                },
            }
        )

        provider = self._provider()
        builder = ContextBuilder(
            self._store,
            provider,
            summary_model=settings.models.fast,
            window_messages=settings.provider.context_window_messages,
            summarize_after=settings.provider.summarize_after_messages,
        )
        context = await builder.build(cid)
        system = SYSTEM_INSTRUCTION
        if context.summary:
            system += "\n\nSummary of the earlier conversation:\n" + context.summary
        tools = self._registry.provider_specs() if settings.provider.tools_enabled else []

        assistant_text = ""
        usage = Usage()
        finish: str | None = None
        persisted = False

        try:
            messages = list(context.messages)
            rounds = 0
            while True:
                calls: list[ToolCall] = []
                round_text = ""
                request = LLMRequest(
                    model=decision.model,
                    messages=messages,
                    system_instruction=system,
                    tools=tools,
                )
                async for chunk in provider.stream(request):
                    if chunk.text:
                        round_text += chunk.text
                        # Accumulate immediately so a mid-stream cancellation
                        # still has something to persist.
                        assistant_text += chunk.text
                        await emit(
                            {"type": "chat.delta", "data": {"id": stream_id, "text": chunk.text}}
                        )
                    if chunk.tool_calls and tools:
                        calls.extend(chunk.tool_calls)
                    if chunk.usage is not None:
                        usage = chunk.usage
                    if chunk.finish_reason:
                        finish = chunk.finish_reason

                if not calls or rounds >= MAX_TOOL_ROUNDS:
                    break

                rounds += 1
                messages.append(Message(role="model", text=round_text, tool_calls=tuple(calls)))
                for call in calls:
                    result = await self._executor.execute(call)
                    self._log.info(
                        "tool %s -> %s (%sms)", result.name, result.status, result.duration_ms
                    )
                    await emit(
                        {
                            "type": "chat.tool",
                            "data": {
                                "id": stream_id,
                                "name": result.name,
                                "args": result.args,
                                "status": result.status,
                                "detail": result.detail,
                                "ms": result.duration_ms,
                            },
                        }
                    )
                    messages.append(
                        Message(
                            role="tool",
                            text=result.detail,
                            tool_name=result.name,
                            tool_response={"status": result.status, "result": result.detail},
                        )
                    )

            if finish == "SAFETY":
                raise SafetyBlockError("response blocked by safety filters")

            cost = self._record(cid, decision.model, assistant_text, usage, settings)
            summary_cost = self._record_summary(cid, context, settings)
            persisted = True
            await emit(
                {
                    "type": "chat.usage",
                    "data": self._usage_payload(
                        stream_id, decision.model, usage, cost, settings, summary_cost
                    ),
                }
            )
            await emit(
                {
                    "type": "chat.done",
                    "data": {"id": stream_id, "model": decision.model, "finish_reason": finish},
                }
            )
            outcome.text = assistant_text
            return outcome

        except ProviderError as exc:
            self._log.warning("provider error (%s): %s", exc.kind, exc)
            outcome.error_kind = exc.kind
            if assistant_text:
                self._record(cid, decision.model, assistant_text, usage, settings)
            else:
                self._store.add_message(
                    cid, "model", exc.friendly, model=decision.model, error_kind=exc.kind
                )
            persisted = True
            await emit(
                {
                    "type": "chat.error",
                    "data": {"id": stream_id, "kind": exc.kind, "message": exc.friendly},
                }
            )
            return outcome

        except asyncio.CancelledError:
            outcome.aborted = True
            raise

        except Exception as exc:
            # Anything that is not a typed ProviderError must still reach the UI,
            # otherwise the stream silently hangs with no chat.done or chat.error.
            self._log.exception("chat pipeline failed: %s", exc)
            outcome.error_kind = "unknown"
            message = "Something went wrong while handling that message. Please try again."
            if assistant_text:
                self._record(cid, decision.model, assistant_text, usage, settings)
            else:
                self._store.add_message(
                    cid, "model", message, model=decision.model, error_kind="unknown"
                )
            persisted = True
            await emit(
                {
                    "type": "chat.error",
                    "data": {"id": stream_id, "kind": "unknown", "message": message},
                }
            )
            return outcome

        finally:
            # Runs even on cancellation: never lose what was already streamed.
            if not persisted and assistant_text:
                self._record(cid, decision.model, assistant_text, usage, settings)

    # -- helpers -----------------------------------------------------------
    def _resolve(self, text: str, settings: Settings, override: str | None) -> RoutingDecision:
        mode: RoutingMode = settings.models.routing
        if override == "fast":
            mode = "fast"
        elif override == "strong":
            mode = "strong"
        return choose_model(
            text,
            fast_model=settings.models.fast,
            strong_model=settings.models.strong,
            mode=mode,
        )

    def _record(
        self, cid: str, model: str, text: str, usage: Usage, settings: Settings
    ) -> float | None:
        cost = estimate_cost(self._price_table, model, usage, tier=settings.pricing.tier)
        self._store.add_message(
            cid,
            "model",
            text,
            model=model,
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost_usd=cost,
        )
        self._usage.record(
            model=model,
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost_usd=cost,
            tier=settings.pricing.tier,
            conversation_id=cid,
        )
        return cost

    def _record_summary(self, cid: str, context: Context, settings: Settings) -> float | None:
        if context.summary_usage is None:
            return None
        cost = estimate_cost(
            self._price_table,
            settings.models.fast,
            context.summary_usage,
            tier=settings.pricing.tier,
        )
        self._usage.record(
            model=settings.models.fast,
            tokens_in=context.summary_usage.input_tokens,
            tokens_out=context.summary_usage.output_tokens,
            cost_usd=cost,
            tier=settings.pricing.tier,
            conversation_id=cid,
        )
        return cost

    def _usage_payload(
        self,
        stream_id: str,
        model: str,
        usage: Usage,
        cost: float | None,
        settings: Settings,
        summary_cost: float | None,
    ) -> dict[str, Any]:
        total = None if cost is None else cost + (summary_cost or 0.0)
        budget = BudgetGuard(self._usage, settings.limits).status()
        return {
            "id": stream_id,
            "model": model,
            "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens,
            "thoughts_tokens": usage.thoughts_tokens,
            "cost_usd": total,
            "cost_known": total is not None,
            "tier": settings.pricing.tier,
            "summary_cost_usd": summary_cost,
            "budget": budget.to_dict(),
        }

    async def _answer_locally(
        self, cid: str, intent: LocalIntent, emit: Emit, outcome: ChatOutcome
    ) -> ChatOutcome:
        stream_id = f"m{next(_stream_ids)}"
        outcome.model = LOCAL_MODEL
        outcome.text = intent.reply
        await emit(
            {
                "type": "chat.start",
                "data": {
                    "id": stream_id,
                    "model": LOCAL_MODEL,
                    "tier": "local",
                    "reason": f"local intent: {intent.name}",
                    "conversation_id": cid,
                },
            }
        )
        await emit({"type": "chat.delta", "data": {"id": stream_id, "text": intent.reply}})
        self._store.add_message(
            cid, "model", intent.reply, model=LOCAL_MODEL, cost_usd=0.0, local=True
        )
        settings = self._settings()
        await emit(
            {
                "type": "chat.usage",
                "data": {
                    "id": stream_id,
                    "model": LOCAL_MODEL,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "thoughts_tokens": 0,
                    "cost_usd": 0.0,
                    "cost_known": True,
                    "tier": "local",
                    "summary_cost_usd": None,
                    "budget": BudgetGuard(self._usage, settings.limits).status().to_dict(),
                },
            }
        )
        await emit(
            {
                "type": "chat.done",
                "data": {
                    "id": stream_id,
                    "model": LOCAL_MODEL,
                    "finish_reason": "LOCAL",
                    "local": True,
                },
            }
        )
        return outcome
