"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from nova.security import redaction


@pytest.fixture(autouse=True)
def _reset_redaction_literals():
    """Keep registered secret literals from leaking across tests."""
    redaction.reset_registered_secrets()
    yield
    redaction.reset_registered_secrets()


@pytest.fixture(autouse=True)
def _isolate_secret_env(monkeypatch):
    """Hide any real secrets present in the developer's environment.

    Covers both the app-specific names and the unprefixed legacy names, so a
    stray variable on the host can never leak into a test.
    """
    for name in (
        "NOVA_GEMINI_API_KEY",
        "NOVA_ELEVENLABS_API_KEY",
        "NOVA_ELEVENLABS_VOICE_ID",
        "GEMINI_API_KEY",
        "ELEVENLABS_API_KEY",
        "ELEVENLABS_VOICE_ID",
    ):
        monkeypatch.delenv(name, raising=False)
