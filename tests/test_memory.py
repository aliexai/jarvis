"""Persistence and budget tests."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from nova.budget import BudgetGuard
from nova.config.settings import LimitSettings
from nova.memory import ChatStore, Database, UsageStore


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "memory.db")
    yield database
    database.close()


def test_conversation_and_messages_roundtrip(db):
    store = ChatStore(db)
    cid = store.create_conversation(title="First")
    store.add_message(cid, "user", "hello")
    store.add_message(
        cid, "model", "hi there", model="m1", tokens_in=5, tokens_out=3, cost_usd=0.001
    )

    rows = store.recent_messages(cid, 10)

    assert [row.role for row in rows] == ["user", "model"]
    assert rows[1].model == "m1"
    assert rows[1].tokens_out == 3
    assert rows[1].cost_usd == pytest.approx(0.001)
    assert store.count_messages(cid) == 2


def test_tool_metadata_is_persisted(db):
    store = ChatStore(db)
    cid = store.create_conversation()
    store.add_message(
        cid,
        "model",
        "done",
        tool_name="get_time",
        tool_args={"x": 1},
        tool_result="2026-01-01T00:00:00",
        tool_ms=12,
    )

    row = store.recent_messages(cid, 5)[-1]
    assert row.tool_name == "get_time"
    assert row.tool_args == '{"x": 1}'
    assert row.tool_ms == 12


def test_ensure_conversation_creates_only_when_missing(db):
    store = ChatStore(db)
    created = store.ensure_conversation(None)
    assert store.ensure_conversation(created) == created
    assert store.ensure_conversation("does-not-exist") != "does-not-exist"


def test_title_is_set_once(db):
    store = ChatStore(db)
    cid = store.create_conversation()
    store.set_title(cid, "First title")
    store.set_title(cid, "Second title")
    assert store.list_conversations()[0]["title"] == "First title"


def test_messages_between_window(db):
    store = ChatStore(db)
    cid = store.create_conversation()
    ids = [store.add_message(cid, "user", f"m{i}") for i in range(6)]

    middle = store.messages_between(cid, after_id=ids[0], before_id=ids[4])

    assert [m.content for m in middle] == ["m1", "m2", "m3"]


def test_summary_roundtrip(db):
    store = ChatStore(db)
    cid = store.create_conversation()
    assert store.get_summary(cid) == (None, 0)

    store.set_summary(cid, "they discussed widgets", 7)

    assert store.get_summary(cid) == ("they discussed widgets", 7)


def test_usage_totals(db):
    usage = UsageStore(db)
    usage.record(model="m", tokens_in=10, tokens_out=5, cost_usd=0.5, tier="paid")
    usage.record(model="m", tokens_in=10, tokens_out=5, cost_usd=0.25, tier="paid")

    totals = usage.totals()

    assert totals.today_usd == pytest.approx(0.75)
    assert totals.requests_today == 2
    assert totals.tokens_today == 30
    assert totals.unknown_cost_today == 0


def test_unknown_cost_is_counted_not_hidden(db):
    usage = UsageStore(db)
    usage.record(model="mystery-model", tokens_in=1, tokens_out=1, cost_usd=None, tier="paid")

    totals = usage.totals()

    assert totals.today_usd == 0.0
    assert totals.unknown_cost_today == 1


def test_month_totals_ignore_older_months(db):
    usage = UsageStore(db)
    usage.record(model="m", tokens_in=1, tokens_out=1, cost_usd=1.0, tier="paid")
    last_month = (datetime.now().replace(day=1) - timedelta(days=40)).isoformat(timespec="seconds")
    usage.record(model="m", tokens_in=1, tokens_out=1, cost_usd=9.0, tier="paid", at=last_month)

    totals = usage.totals()

    assert totals.month_usd == pytest.approx(1.0)


def test_budget_blocks_when_daily_limit_reached(db):
    usage = UsageStore(db)
    usage.record(model="m", tokens_in=0, tokens_out=0, cost_usd=2.0, tier="paid")
    guard = BudgetGuard(usage, LimitSettings(daily_usd=1.0, monthly_usd=100.0, hard_stop=True))

    status = guard.status()

    assert status.allowed is False
    assert "daily" in status.reason


def test_budget_blocks_when_monthly_limit_reached(db):
    usage = UsageStore(db)
    usage.record(model="m", tokens_in=0, tokens_out=0, cost_usd=50.0, tier="paid")
    guard = BudgetGuard(
        usage,
        LimitSettings(daily_usd=1000.0, monthly_usd=10.0, hard_stop=True),
    )

    status = guard.status()

    assert status.allowed is False
    assert "monthly" in status.reason


def test_budget_soft_mode_never_blocks(db):
    usage = UsageStore(db)
    usage.record(model="m", tokens_in=0, tokens_out=0, cost_usd=99.0, tier="paid")
    guard = BudgetGuard(usage, LimitSettings(daily_usd=1.0, monthly_usd=1.0, hard_stop=False))
    assert guard.status().allowed is True


def test_budget_disabled_never_blocks(db):
    usage = UsageStore(db)
    usage.record(model="m", tokens_in=0, tokens_out=0, cost_usd=99.0, tier="paid")
    guard = BudgetGuard(
        usage, LimitSettings(enabled=False, daily_usd=1.0, monthly_usd=1.0, hard_stop=True)
    )
    assert guard.status().allowed is True
