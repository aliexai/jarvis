"""Usage and cost accounting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nova.memory.db import Database


def _local_now() -> datetime:
    return datetime.now()


@dataclass(frozen=True)
class UsageTotals:
    today_usd: float
    month_usd: float
    requests_today: int
    tokens_today: int
    unknown_cost_today: int


class UsageStore:
    """Records per-request usage and aggregates it by day and month."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def _conn(self):
        return self._db.connection

    def record(
        self,
        *,
        model: str,
        tokens_in: int,
        tokens_out: int,
        cost_usd: float | None,
        tier: str,
        conversation_id: str | None = None,
        at: str | None = None,
    ) -> None:
        stamp = at or _local_now().isoformat(timespec="seconds")
        with self._db.lock, self._conn:
            self._conn.execute(
                "INSERT INTO usage (at, conversation_id, model, tokens_in, tokens_out,"
                " cost_usd, tier) VALUES (?,?,?,?,?,?,?)",
                (stamp, conversation_id, model, tokens_in, tokens_out, cost_usd, tier),
            )

    def totals(self, when: datetime | None = None) -> UsageTotals:
        moment = when or _local_now()
        day = moment.strftime("%Y-%m-%d")
        month = moment.strftime("%Y-%m")

        with self._db.lock:
            today = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS cost, COUNT(*) AS n,"
                " COALESCE(SUM(tokens_in + tokens_out), 0) AS tokens,"
                " SUM(CASE WHEN cost_usd IS NULL THEN 1 ELSE 0 END) AS unknown"
                " FROM usage WHERE substr(at, 1, 10) = ?",
                (day,),
            ).fetchone()
            month_row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) AS cost FROM usage WHERE substr(at, 1, 7) = ?",
                (month,),
            ).fetchone()

        return UsageTotals(
            today_usd=float(today["cost"] or 0.0),
            month_usd=float(month_row["cost"] or 0.0),
            requests_today=int(today["n"] or 0),
            tokens_today=int(today["tokens"] or 0),
            unknown_cost_today=int(today["unknown"] or 0),
        )

    def recent(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._db.lock:
            rows = self._conn.execute(
                "SELECT at, model, tokens_in, tokens_out, cost_usd, tier FROM usage"
                " ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
