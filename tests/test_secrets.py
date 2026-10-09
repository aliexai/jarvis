"""Tests for the secret store: lookup order, source reporting, prefix checks."""

from __future__ import annotations

import pytest

from fakes import FakeBackend
from nova.errors import SecretError
from nova.security.redaction import REDACTED, redact_text
from nova.security.secrets import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    GEMINI_API_KEY,
    SOURCE_DOTENV,
    SOURCE_ENV,
    SOURCE_KEYRING,
    SOURCE_NONE,
    SecretStore,
    ignored_legacy_env,
)

GOOGLE_KEY = "AIzaSyABCDEFGHIJKLMNOP1234567890"
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"


def _store(tmp_path, *, backend=None, environ=None) -> SecretStore:
    return SecretStore(
        backend=backend if backend is not None else FakeBackend(),
        dotenv_path=tmp_path / "missing.env",
        environ={} if environ is None else environ,
    )


# -- basic CRUD ------------------------------------------------------------


def test_set_get_has_delete(tmp_path):
    store = _store(tmp_path)
    store.set(GEMINI_API_KEY, GOOGLE_KEY)
    assert store.get(GEMINI_API_KEY) == GOOGLE_KEY
    assert store.has(GEMINI_API_KEY) is True

    store.delete(GEMINI_API_KEY)
    assert store.get(GEMINI_API_KEY) is None
    assert store.has(GEMINI_API_KEY) is False


def test_set_without_backend_raises(tmp_path):
    store = SecretStore(use_keyring=False, dotenv_path=tmp_path / "missing.env", environ={})
    with pytest.raises(SecretError):
        store.set(GEMINI_API_KEY, "value-123456")


def test_delete_missing_is_tolerated(tmp_path):
    _store(tmp_path).delete(GEMINI_API_KEY)  # must not raise


# -- lookup order ----------------------------------------------------------


def test_keyring_wins_over_dotenv_and_env(tmp_path):
    backend = FakeBackend()
    backend.set_password("Nova", GEMINI_API_KEY, "AIza-from-keyring-1234567890")
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(f"{GEMINI_API_KEY}=AIza-from-dotenv-1234567890\n", encoding="utf-8")
    store = SecretStore(
        backend=backend,
        dotenv_path=dotenv_file,
        environ={GEMINI_API_KEY: "AIza-from-env-1234567890"},
    )

    resolved = store.resolve(GEMINI_API_KEY)
    assert resolved.value == "AIza-from-keyring-1234567890"
    assert resolved.source == SOURCE_KEYRING


def test_dotenv_wins_over_env(tmp_path):
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(f"{GEMINI_API_KEY}=AIza-from-dotenv-1234567890\n", encoding="utf-8")
    store = SecretStore(
        backend=FakeBackend(),
        dotenv_path=dotenv_file,
        environ={GEMINI_API_KEY: "AIza-from-env-1234567890"},
    )

    resolved = store.resolve(GEMINI_API_KEY)
    assert resolved.value == "AIza-from-dotenv-1234567890"
    assert resolved.source == SOURCE_DOTENV


def test_env_is_last_resort(tmp_path):
    store = _store(tmp_path, environ={GEMINI_API_KEY: GOOGLE_KEY})
    resolved = store.resolve(GEMINI_API_KEY)
    assert resolved.value == GOOGLE_KEY
    assert resolved.source == SOURCE_ENV


def test_source_is_not_set_when_absent(tmp_path):
    resolved = _store(tmp_path).resolve(GEMINI_API_KEY)
    assert resolved.value is None
    assert resolved.source == SOURCE_NONE
    assert resolved.masked == "(not set)"


def test_unprefixed_legacy_env_is_ignored(tmp_path):
    environ = {"GEMINI_API_KEY": "sk-or-v1-unrelated-1234567890"}
    store = _store(tmp_path, environ=environ)
    # The app-specific name is unaffected by the unrelated legacy variable.
    assert store.get(GEMINI_API_KEY) is None
    assert ignored_legacy_env(environ) == ["GEMINI_API_KEY"]


# -- prefix sanity checks --------------------------------------------------


def test_gemini_google_prefix_is_accepted(tmp_path):
    store = _store(tmp_path, environ={GEMINI_API_KEY: GOOGLE_KEY})
    ok, warning = store.resolve(GEMINI_API_KEY).prefix_check()
    assert ok is True
    assert warning is None


def test_gemini_slot_with_openrouter_key_warns(tmp_path):
    store = _store(tmp_path, environ={GEMINI_API_KEY: "sk-or-v1-not-a-google-key-123456"})
    ok, warning = store.resolve(GEMINI_API_KEY).prefix_check()
    assert ok is False
    assert warning is not None
    assert "AIza" in warning
    assert "sk-or-" in warning


def test_elevenlabs_prefix_mismatch_warns(tmp_path):
    store = _store(tmp_path, environ={ELEVENLABS_API_KEY: "sk-or-v1-wrong-provider-1234567890"})
    ok, warning = store.resolve(ELEVENLABS_API_KEY).prefix_check()
    assert ok is False
    assert warning is not None


def test_voice_id_has_no_prefix_requirement(tmp_path):
    store = _store(tmp_path, environ={ELEVENLABS_VOICE_ID: VOICE_ID})
    assert store.resolve(ELEVENLABS_VOICE_ID).prefix_check() == (True, None)


# -- redaction integration -------------------------------------------------


def test_retrieved_secret_is_registered_for_redaction(tmp_path):
    secret = "opaque-secret-abcdef1234567890"
    store = _store(tmp_path)
    store.set(GEMINI_API_KEY, secret)
    assert store.get(GEMINI_API_KEY) == secret
    assert redact_text(secret) == REDACTED


def test_masked_never_reveals_key_material(tmp_path):
    store = _store(tmp_path)
    store.set(GEMINI_API_KEY, GOOGLE_KEY)
    masked = store.masked(GEMINI_API_KEY)
    assert masked == f"(set, {len(GOOGLE_KEY)} chars)"
    assert GOOGLE_KEY not in masked
    assert "AIza" not in masked
