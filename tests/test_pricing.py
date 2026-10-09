"""Price table and cost estimation tests."""

from __future__ import annotations

import json

import pytest

from nova.providers.base import Usage
from nova.providers.pricing import (
    PRICES_LAST_CHECKED,
    builtin_table,
    estimate_cost,
    format_cost,
    load_price_table,
)

MILLION = 1_000_000


def _usage(inp: int = 0, out: int = 0) -> Usage:
    return Usage(input_tokens=inp, output_tokens=out, total_tokens=inp + out)


def test_price_table_records_when_it_was_checked():
    table = builtin_table()
    assert table.last_checked == PRICES_LAST_CHECKED == "2026-10-09"
    assert table.source.startswith("https://ai.google.dev/")


def test_paid_cost_matches_the_published_rates():
    table = builtin_table()
    cost = estimate_cost(table, "gemini-3.8-flash", _usage(MILLION, MILLION), tier="paid")
    assert cost == pytest.approx(0.75 + 3.75)


def test_flash_lite_is_cheaper_than_flash():
    table = builtin_table()
    lite = estimate_cost(table, "gemini-3.5-flash-lite", _usage(MILLION, MILLION), tier="paid")
    flash = estimate_cost(table, "gemini-3.8-flash", _usage(MILLION, MILLION), tier="paid")
    assert lite is not None and flash is not None
    assert lite < flash


def test_free_tier_costs_nothing():
    table = builtin_table()
    assert estimate_cost(table, "gemini-3.8-flash", _usage(MILLION, MILLION), tier="free") == 0.0


def test_unknown_model_reports_unknown_not_zero():
    table = builtin_table()
    assert estimate_cost(table, "totally-made-up", _usage(10, 10), tier="paid") is None
    assert format_cost(None) == "unknown"


def test_partial_usage_is_proportional():
    table = builtin_table()
    cost = estimate_cost(table, "gemini-3.5-flash-lite", _usage(1000, 500), tier="paid")
    expected = 1000 / MILLION * 0.30 + 500 / MILLION * 2.50
    assert cost == pytest.approx(expected)


def test_format_cost_edges():
    assert format_cost(0.0) == "$0.00"
    assert format_cost(0.0012) == "$0.0012"
    assert format_cost(1.239) == "$1.24"


def test_override_file_extends_and_keeps_builtins(tmp_path):
    override = tmp_path / "prices.json"
    override.write_text(
        json.dumps(
            {
                "last_checked": "2027-01-01",
                "models": {"custom-model": {"input_per_million": 1.0, "output_per_million": 2.0}},
            }
        ),
        encoding="utf-8",
    )

    table = load_price_table(override)

    assert table.last_checked == "2027-01-01"
    assert table.price_for("custom-model") is not None
    assert table.price_for("gemini-3.8-flash") is not None


def test_missing_override_file_is_ignored(tmp_path):
    table = load_price_table(tmp_path / "nope.json")
    assert table.last_checked == PRICES_LAST_CHECKED


def test_malformed_override_file_is_ignored(tmp_path):
    override = tmp_path / "prices.json"
    override.write_text("{not json", encoding="utf-8")
    assert load_price_table(override).last_checked == PRICES_LAST_CHECKED
