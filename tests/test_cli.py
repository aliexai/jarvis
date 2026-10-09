"""Tests for the diagnostics command output."""

from __future__ import annotations

import json

from fakes import FakeBackend
from nova.cli import _diagnostics
from nova.security.secrets import GEMINI_API_KEY, SOURCE_ENV, SecretStore


def test_diagnostics_reports_ignored_env_and_prefix(tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "sk-or-v1-legacy-must-be-ignored-123456")
    store = SecretStore(
        backend=FakeBackend(),
        dotenv_path=tmp_path / "missing.env",
        environ={GEMINI_API_KEY: "sk-or-v1-wrong-provider-1234567890"},
    )

    report = _diagnostics(store=store)

    entry = report["secrets"][GEMINI_API_KEY]
    assert entry["source"] == SOURCE_ENV
    assert entry["prefix_ok"] is False
    # No key characters beyond a public prefix may appear anywhere in the report.
    serialized = json.dumps(report)
    assert "1234567890" not in serialized
    assert any("expected provider prefix" in warning for warning in report["warnings"])
    assert any("ignoring unprefixed" in warning for warning in report["warnings"])
