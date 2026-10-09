"""Conversation and message persistence, plus rolling summaries."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from nova.memory.db import Database


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass(frozen=True)
class StoredMessage:
    id: int
    conversation_id: str
    role: str
    content: str
    model: str | None
    created_at: str
    tokens_in: int
    tokens_out: int
    cost_usd: float | None
    tool_name: str | None
    tool_args: str | None
    tool_result: str | None
    tool_ms: int | None
    error_kind: str | None
    local: bool


class ChatStore:
    """CRUD for conversations and their messages."""

    def __init__(self, db: Database) -> None:
        self._db = db

    @property
    def _conn(self):
        return self._db.connection

    # -- conversations -----------------------------------------------------
    def create_conversation(self, *, title: str | None = None, model: str | None = None) -> str:
        conversation_id = uuid.uuid4().hex
        stamp = now_iso()
        with self._db.lock, self._conn:
            self._conn.execute(
                "INSERT INTO conversations (id, created_at, updated_at, title, model)"
                " VALUES (?, ?, ?, ?, ?)",
                (conversation_id, stamp, stamp, title, model),
            )
        return conversation_id

    def ensure_conversation(self, conversation_id: str | None) -> str:
        if conversation_id:
            with self._db.lock:
                row = self._conn.execute(
                    "SELECT id FROM conversations WHERE id = ?", (conversation_id,)
                ).fetchone()
            if row is not None:
                return conversation_id
        return self.create_conversation()

    def set_title(self, conversation_id: str, title: str) -> None:
        with self._db.lock, self._conn:
            self._conn.execute(
                "UPDATE conversations SET title = ? WHERE id = ? AND (title IS NULL OR title = '')",
                (title[:80], conversation_id),
            )

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._db.lock:
            rows = self._conn.execute(
                "SELECT id, created_at, updated_at, title, model FROM conversations"
                " ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    # -- messages ----------------------------------------------------------
    def add_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        *,
        model: str | None = None,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float | None = None,
        tool_name: str | None = None,
        tool_args: dict[str, Any] | None = None,
        tool_result: str | None = None,
        tool_ms: int | None = None,
        error_kind: str | None = None,
        local: bool = False,
    ) -> int:
        stamp = now_iso()
        with self._db.lock, self._conn:
            cursor = self._conn.execute(
                "INSERT INTO messages (conversation_id, role, content, model, created_at,"
                " tokens_in, tokens_out, cost_usd, tool_name, tool_args, tool_result, tool_ms,"
                " error_kind, local) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    conversation_id,
                    role,
                    content,
                    model,
                    stamp,
                    tokens_in,
                    tokens_out,
                    cost_usd,
                    tool_name,
                    json.dumps(tool_args, ensure_ascii=False) if tool_args is not None else None,
                    tool_result,
                    tool_ms,
                    error_kind,
                    1 if local else 0,
                ),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at = ? WHERE id = ?",
                (stamp, conversation_id),
            )
            return int(cursor.lastrowid or 0)

    def recent_messages(self, conversation_id: str, limit: int) -> list[StoredMessage]:
        with self._db.lock:
            rows = self._conn.execute(
                "SELECT * FROM messages WHERE conversation_id = ? ORDER BY id DESC LIMIT ?",
                (conversation_id, limit),
            ).fetchall()
        return [_to_message(row) for row in reversed(rows)]

    def messages_between(
        self, conversation_id: str, after_id: int, before_id: int | None = None
    ) -> list[StoredMessage]:
        sql = "SELECT * FROM messages WHERE conversation_id = ? AND id > ?"
        params: list[Any] = [conversation_id, after_id]
        if before_id is not None:
            sql += " AND id < ?"
            params.append(before_id)
        sql += " ORDER BY id ASC"
        with self._db.lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_to_message(row) for row in rows]

    def count_messages(self, conversation_id: str) -> int:
        with self._db.lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        return int(row["n"]) if row else 0

    def last_message_id(self, conversation_id: str) -> int:
        with self._db.lock:
            row = self._conn.execute(
                "SELECT MAX(id) AS n FROM messages WHERE conversation_id = ?", (conversation_id,)
            ).fetchone()
        return int(row["n"] or 0) if row else 0

    # -- summaries ---------------------------------------------------------
    def get_summary(self, conversation_id: str) -> tuple[str | None, int]:
        with self._db.lock:
            row = self._conn.execute(
                "SELECT summary, summary_upto_id FROM conversations WHERE id = ?",
                (conversation_id,),
            ).fetchone()
        if row is None:
            return None, 0
        return row["summary"], int(row["summary_upto_id"] or 0)

    def set_summary(self, conversation_id: str, summary: str, upto_id: int) -> None:
        with self._db.lock, self._conn:
            self._conn.execute(
                "UPDATE conversations SET summary = ?, summary_upto_id = ? WHERE id = ?",
                (summary, upto_id, conversation_id),
            )


def _to_message(row) -> StoredMessage:
    return StoredMessage(
        id=int(row["id"]),
        conversation_id=row["conversation_id"],
        role=row["role"],
        content=row["content"],
        model=row["model"],
        created_at=row["created_at"],
        tokens_in=int(row["tokens_in"] or 0),
        tokens_out=int(row["tokens_out"] or 0),
        cost_usd=row["cost_usd"],
        tool_name=row["tool_name"],
        tool_args=row["tool_args"],
        tool_result=row["tool_result"],
        tool_ms=row["tool_ms"],
        error_kind=row["error_kind"],
        local=bool(row["local"]),
    )
