"""Model routing: pick the cheap model for routine turns and the strong model
for coding, planning and long reasoning, unless the user overrides it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

RoutingMode = Literal["auto", "fast", "strong"]

# Long inputs are worth the strong model.
LONG_INPUT_CHARS = 320

_CODE_HINTS = (
    "```",
    "def ",
    "class ",
    "function",
    "traceback",
    "stack trace",
    "compile",
    "refactor",
    "unit test",
    "pytest",
    "regex",
    "sql",
    "bug",
)
_PLANNING_HINTS = (
    "plan",
    "architect",
    "design",
    "step by step",
    "step-by-step",
    "roadmap",
    "why does",
    "explain how",
    "trade-off",
    "tradeoff",
    "compare",
    "strategy",
    "prove",
    "derive",
)


@dataclass(frozen=True)
class RoutingDecision:
    model: str
    tier: Literal["fast", "strong"]
    reason: str
    # True when the routing was forced rather than chosen by the heuristic.
    forced: bool = False


def choose_model(
    text: str,
    *,
    fast_model: str,
    strong_model: str,
    mode: RoutingMode = "auto",
) -> RoutingDecision:
    """Decide which model should answer ``text``."""
    if mode == "fast":
        return RoutingDecision(fast_model, "fast", "manual override: fast", forced=True)
    if mode == "strong":
        return RoutingDecision(strong_model, "strong", "manual override: strong", forced=True)

    lowered = text.lower()
    if len(text) > LONG_INPUT_CHARS:
        return RoutingDecision(strong_model, "strong", "long input")
    if any(hint in lowered for hint in _CODE_HINTS):
        return RoutingDecision(strong_model, "strong", "coding task")
    if any(hint in lowered for hint in _PLANNING_HINTS):
        return RoutingDecision(strong_model, "strong", "planning/reasoning task")
    if lowered.count("?") >= 3:
        return RoutingDecision(strong_model, "strong", "multi-part question")
    return RoutingDecision(fast_model, "fast", "simple request")
