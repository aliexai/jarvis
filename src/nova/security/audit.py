"""Tamper-evident audit log.

Every security-relevant action is appended to a SQLite table forming a hash
chain: each row stores the hash of the previous row and a hash of its own
canonical contents. Editing, reordering or deleting any row breaks
:meth:`AuditLog.verify_chain`, which reports the first offending row id.

The log records *decisions*, not secrets - callers must pass already-safe
strings, and the redactor guards the rest.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from nova.security.redaction import redact_text

GENESIS_HASH = "0" * 64

_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    ts        TEXT    NOT NULL,
    actor     TEXT    NOT NULL,
    action    TEXT    NOT NULL,
    target    TEXT,
    decision  TEXT    NOT NULL,
    detail    TEXT,
    prev_hash TEXT    NOT NULL,
    hash      TEXT    NOT NULL
);
"""


@dataclass(frozen=True)
class AuditEntry:
    id: int
    ts: str
    actor: str
    action: str
    target: str | None
    decision: str
    detail: str | None
    prev_hash: str
    hash: str


class AuditLog:
    """Append-only, hash-chained audit log backed by SQLite (WAL mode)."""

    def __init__(self, db_path: Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._closed = False
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(_SCHEMA)

    # -- hashing -----------------------------------------------------------
    @staticmethod
    def _canonical(
        ts: str,
        actor: str,
        action: str,
        target: str | None,
        decision: str,
        detail: str | None,
    ) -> str:
        return json.dumps(
            {
                "ts": ts,
                "actor": actor,
                "action": action,
                "target": target,
                "decision": decision,
                "detail": detail,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _hash(prev_hash: str, canonical: str) -> str:
        return hashlib.sha256(f"{prev_hash}|{canonical}".encode()).hexdigest()

    # -- public API --------------------------------------------------------
    def append(
        self,
        actor: str,
        action: str,
        target: str | None = None,
        decision: str = "info",
        detail: str | None = None,
        ts: str | None = None,
    ) -> str:
        """Append an entry and return its hash.

        ``target`` and ``detail`` are passed through the redactor first, so a
        secret can never be persisted to the audit log even by accident.
        """
        target = redact_text(target) if target else target
        detail = redact_text(detail) if detail else detail
        timestamp = ts if ts is not None else f"{time.time():.6f}"
        with self._lock, self._conn:
            row = self._conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
            prev_hash = row["hash"] if row else GENESIS_HASH
            canonical = self._canonical(timestamp, actor, action, target, decision, detail)
            entry_hash = self._hash(prev_hash, canonical)
            self._conn.execute(
                "INSERT INTO audit (ts, actor, action, target, decision, detail, prev_hash, hash)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (timestamp, actor, action, target, decision, detail, prev_hash, entry_hash),
            )
        return entry_hash

    def entries(self, limit: int = 100) -> list[AuditEntry]:
        """Return the most recent ``limit`` entries, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            AuditEntry(
                id=row["id"],
                ts=row["ts"],
                actor=row["actor"],
                action=row["action"],
                target=row["target"],
                decision=row["decision"],
                detail=row["detail"],
                prev_hash=row["prev_hash"],
                hash=row["hash"],
            )
            for row in reversed(rows)
        ]

    def verify_chain(self) -> tuple[bool, int | None]:
        """Verify integrity. Returns ``(ok, first_bad_id)``."""
        with self._lock:
            rows = self._conn.execute("SELECT * FROM audit ORDER BY id ASC").fetchall()
        prev_hash = GENESIS_HASH
        for row in rows:
            canonical = self._canonical(
                row["ts"],
                row["actor"],
                row["action"],
                row["target"],
                row["decision"],
                row["detail"],
            )
            if row["prev_hash"] != prev_hash or row["hash"] != self._hash(prev_hash, canonical):
                return False, row["id"]
            prev_hash = row["hash"]
        return True, None

    def close(self) -> None:
        """Close the underlying connection. Idempotent."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._conn.close()
