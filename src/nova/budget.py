"""Cost limits: a soft budget the user sets, with an optional hard stop.

Unknown prices are surfaced rather than treated as zero, so a model missing from
the price table never silently looks free.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from nova.config.settings import LimitSettings
from nova.memory.usage import UsageStore


@dataclass(frozen=True)
class BudgetStatus:
    allowed: bool
    reason: str
    today_usd: float
    month_usd: float
    daily_limit: float
    monthly_limit: float
    hard_stop: bool
    requests_today: int
    tokens_today: int
    unknown_cost_today: int

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "today_usd": round(self.today_usd, 6),
            "month_usd": round(self.month_usd, 6),
            "daily_limit": self.daily_limit,
            "monthly_limit": self.monthly_limit,
            "hard_stop": self.hard_stop,
            "requests_today": self.requests_today,
            "tokens_today": self.tokens_today,
            "unknown_cost_today": self.unknown_cost_today,
        }


class BudgetGuard:
    """Decides whether a request may proceed, and reports running totals."""

    def __init__(self, usage: UsageStore, limits: LimitSettings) -> None:
        self._usage = usage
        self._limits = limits

    def status(self) -> BudgetStatus:
        totals = self._usage.totals()
        limits = self._limits

        base: dict[str, Any] = dict(
            today_usd=totals.today_usd,
            month_usd=totals.month_usd,
            daily_limit=limits.daily_usd,
            monthly_limit=limits.monthly_usd,
            hard_stop=limits.hard_stop,
            requests_today=totals.requests_today,
            tokens_today=totals.tokens_today,
            unknown_cost_today=totals.unknown_cost_today,
        )

        if not limits.enabled:
            return BudgetStatus(allowed=True, reason="limits disabled", **base)
        if limits.hard_stop and totals.month_usd >= limits.monthly_usd > 0:
            return BudgetStatus(
                allowed=False,
                reason=f"monthly limit of ${limits.monthly_usd:.2f} reached",
                **base,
            )
        if limits.hard_stop and totals.today_usd >= limits.daily_usd > 0:
            return BudgetStatus(
                allowed=False,
                reason=f"daily limit of ${limits.daily_usd:.2f} reached",
                **base,
            )
        return BudgetStatus(allowed=True, reason="within limits", **base)
