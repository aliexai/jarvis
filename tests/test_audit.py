"""Tests for the tamper-evident audit log."""

from __future__ import annotations

import sqlite3

from nova.security.audit import AuditLog
from nova.security.redaction import REDACTED, register_secret


def test_append_and_verify(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    log.append("user", "tool.call", "open_app", "allow", "notepad")
    log.append("agent", "tool.call", "fs.write", "ask", "notes.txt")

    ok, bad = log.verify_chain()
    assert ok is True
    assert bad is None

    entries = log.entries()
    assert [e.action for e in entries] == ["tool.call", "tool.call"]
    assert entries[0].decision == "allow"
    assert entries[1].detail == "notes.txt"
    log.close()


def test_chain_links_entries(tmp_path):
    log = AuditLog(tmp_path / "audit.db")
    first = log.append("user", "a", "t", "allow", "d1")
    second = log.append("user", "b", "t", "allow", "d2")
    rows = log.entries()
    assert rows[0].prev_hash == "0" * 64
    assert rows[1].prev_hash == first
    assert second == rows[1].hash
    log.close()


def test_tampering_is_detected(tmp_path):
    db = tmp_path / "audit.db"
    log = AuditLog(db)
    log.append("user", "a", "t", "allow", "original")
    log.append("user", "b", "t", "allow", "second")
    log.close()

    conn = sqlite3.connect(str(db))
    conn.execute("UPDATE audit SET detail = 'tampered' WHERE id = 1")
    conn.commit()
    conn.close()

    reopened = AuditLog(db)
    ok, bad = reopened.verify_chain()
    assert ok is False
    assert bad == 1
    reopened.close()


def test_entry_removal_is_detected(tmp_path):
    db = tmp_path / "audit.db"
    log = AuditLog(db)
    log.append("user", "a", "t", "allow", "keep")
    log.append("user", "b", "t", "allow", "remove")
    log.append("user", "c", "t", "allow", "keep2")
    log.close()

    conn = sqlite3.connect(str(db))
    conn.execute("DELETE FROM audit WHERE id = 2")
    conn.commit()
    conn.close()

    reopened = AuditLog(db)
    ok, bad = reopened.verify_chain()
    assert ok is False
    assert bad == 3
    reopened.close()


def test_audit_redacts_registered_secret_in_fields(tmp_path):
    secret = "opaque-audit-secret-1234567890"
    register_secret(secret)

    log = AuditLog(tmp_path / "audit.db")
    log.append("agent", "net.fetch", "https://api", "allow", f"token={secret}")
    entry = log.entries()[0]

    assert secret not in (entry.detail or "")
    assert REDACTED in (entry.detail or "")
    # Redaction happens before hashing, so the chain stays valid.
    ok, bad = log.verify_chain()
    assert ok is True
    assert bad is None
    log.close()


def test_audit_redacts_pattern_shaped_key_in_target(tmp_path):
    key = "AIzaSyABCDEFGHIJKLMNOP1234567890"
    log = AuditLog(tmp_path / "audit.db")
    log.append("agent", "net.fetch", f"https://api?key={key}", "allow", None)

    entry = log.entries()[0]
    assert key not in (entry.target or "")
    assert REDACTED in (entry.target or "")
    log.close()
