"""Configurable price table and cost estimation.

Prices are **not guessed**: they were transcribed from the official pricing page
on :data:`PRICES_LAST_CHECKED`. Models absent from the table are reported as
``unknown`` rather than being given an invented number.

An optional ``prices.json`` next to the settings file overrides or extends the
built-in table without a code change, e.g.::

    {
      "last_checked": "2026-10-09",
      "source": "https://ai.google.dev/gemini-api/docs/pricing",
      "models": {"gemini-3.8-flash": {"input_per_million": 0.75, "output_per_million": 3.75}}
    }
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from nova.providers.base import Usage

PRICES_LAST_CHECKED = "2026-10-09"
PRICES_SOURCE = "https://ai.google.dev/gemini-api/docs/pricing"

# Paid-tier list prices, USD per 1,000,000 tokens. The free tier is free of
# charge for these models, which is handled by the ``tier`` argument.
_BUILTIN: dict[str, tuple[float, float]] = {
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.7-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3-flash-preview": (0.50, 3.00),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-2.5-pro": (1.25, 10.00),
}


@dataclass(frozen=True)
class ModelPrice:
    input_per_million: float
    output_per_million: float


@dataclass(frozen=True)
class PriceTable:
    last_checked: str
    source: str
    models: dict[str, ModelPrice]

    def price_for(self, model: str) -> ModelPrice | None:
        return self.models.get(model)


def builtin_table() -> PriceTable:
    return PriceTable(
        last_checked=PRICES_LAST_CHECKED,
        source=PRICES_SOURCE,
        models={
            name: ModelPrice(input_per_million=inp, output_per_million=out)
            for name, (inp, out) in _BUILTIN.items()
        },
    )


def load_price_table(override_path: Path | None = None) -> PriceTable:
    """Return the built-in table, merged with an optional override file."""
    table = builtin_table()
    if override_path is None or not Path(override_path).is_file():
        return table

    try:
        document = json.loads(Path(override_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return table

    models = dict(table.models)
    for name, entry in (document.get("models") or {}).items():
        if (
            isinstance(entry, dict)
            and "input_per_million" in entry
            and "output_per_million" in entry
        ):
            models[name] = ModelPrice(
                input_per_million=float(entry["input_per_million"]),
                output_per_million=float(entry["output_per_million"]),
            )
    return PriceTable(
        last_checked=str(document.get("last_checked", table.last_checked)),
        source=str(document.get("source", table.source)),
        models=models,
    )


def estimate_cost(
    table: PriceTable, model: str, usage: Usage, *, tier: str = "free"
) -> float | None:
    """Estimate the cost of one request in USD, or ``None`` if unknown."""
    price = table.price_for(model)
    if price is None:
        return None
    if tier == "free":
        return 0.0
    return (
        usage.input_tokens / 1_000_000 * price.input_per_million
        + usage.output_tokens / 1_000_000 * price.output_per_million
    )


def format_cost(value: float | None) -> str:
    """Render a cost for the UI, or ``unknown`` when the price is not known."""
    if value is None:
        return "unknown"
    if value == 0:
        return "$0.00"
    if value < 0.01:
        return f"${value:.4f}"
    return f"${value:.2f}"
