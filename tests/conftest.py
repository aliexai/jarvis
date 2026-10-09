"""Shared pytest fixtures."""

from __future__ import annotations

import os

import pytest

from nova.security import redaction

# QtWebEngine requires shared OpenGL contexts to be enabled before QApplication
# is constructed (pytest-qt constructs it), otherwise the UI smoke test can
# crash the test process. Also force software rendering in tests.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")
try:  # pragma: no cover - depends on PySide6 being installed
    from PySide6.QtCore import QCoreApplication, Qt

    QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True)
except Exception:
    pass


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


@pytest.fixture
def core_state(tmp_path):
    """A fully isolated CoreState backed by temporary paths and a fake keyring."""
    from fakes import FakeBackend
    from nova.api.state import CoreState
    from nova.config.paths import AppPaths
    from nova.security.secrets import SecretStore

    paths = AppPaths(
        root=tmp_path,
        data=tmp_path / "data",
        config=tmp_path / "config",
        cache=tmp_path / "cache",
        logs=tmp_path / "logs",
    ).ensure()
    store = SecretStore(backend=FakeBackend(), dotenv_path=tmp_path / "missing.env", environ={})
    state = CoreState.create(
        token="test-token",
        paths=paths,
        secrets=store,
        audit_path=tmp_path / "audit.db",
        db_path=tmp_path / "memory.db",
    )
    # API tests must be deterministic and offline.
    state.settings.provider.name = "mock"
    yield state
    state.close()
