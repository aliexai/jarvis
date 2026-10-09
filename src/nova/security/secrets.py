"""Secret storage and resolution.

Resolution order (first hit wins):

1. **Windows Credential Manager** via ``keyring`` - the supported production store.
2. **Project ``.env``** - local development convenience.
3. **System environment variables** - last, for CI or power users.

Names are **app-specific** (``NOVA_`` prefixed). This is deliberate: a machine
may already export an unrelated ``GEMINI_API_KEY`` (for example pointing at a
non-Google provider), and NOVA must never pick that up by accident. The
unprefixed legacy names are only *reported* as ignored, never read.

Values are never returned to a logger unredacted: every value handed out is
first registered with the redactor. The store is injectable (``backend``,
``environ``, ``dotenv_path``) so tests never depend on the host.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from dotenv import dotenv_values

from nova.errors import SecretError
from nova.security.redaction import register_secret

SERVICE_NAME = "Nova"

# App-specific secret names (used for keyring, .env and environment lookups).
GEMINI_API_KEY = "NOVA_GEMINI_API_KEY"
ELEVENLABS_API_KEY = "NOVA_ELEVENLABS_API_KEY"
ELEVENLABS_VOICE_ID = "NOVA_ELEVENLABS_VOICE_ID"

KNOWN_SECRETS: tuple[str, ...] = (GEMINI_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID)

# Unprefixed names that must NOT be read. Kept only so `nova diag` can tell the
# user they exist and are being ignored.
LEGACY_SECRET_ENV: tuple[str, ...] = (
    "GEMINI_API_KEY",
    "ELEVENLABS_API_KEY",
    "ELEVENLABS_VOICE_ID",
)

SOURCE_KEYRING = "keyring"
SOURCE_DOTENV = ".env"
SOURCE_ENV = "system env"
SOURCE_NONE = "not set"

# Expected, non-secret provider prefixes. Used only to flag a value that is
# clearly for a different provider (e.g. an OpenRouter "sk-or-" key in the
# Gemini slot). These are public prefixes, not key material.
EXPECTED_PREFIX: dict[str, str] = {
    GEMINI_API_KEY: "AIza",
    ELEVENLABS_API_KEY: "sk_",
}
KNOWN_PREFIXES: tuple[str, ...] = ("AIza", "sk-or-", "sk_", "sk-", "gsk_", "xai-", "hf_")


class KeyringBackend(Protocol):
    """The subset of the ``keyring`` API that we use."""

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


def detect_prefix(value: str) -> str | None:
    """Return a *known* provider prefix if ``value`` starts with one."""
    for prefix in KNOWN_PREFIXES:
        if value.startswith(prefix):
            return prefix
    return None


def find_project_dotenv(start: Path | None = None) -> Path | None:
    """Walk up from ``start`` (default: cwd) looking for a ``.env`` file."""
    base = (start or Path.cwd()).resolve()
    for directory in (base, *base.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
    return None


def ignored_legacy_env(environ: dict[str, str] | os._Environ[str] | None = None) -> list[str]:
    """Return unprefixed secret env vars that exist but are deliberately ignored."""
    env = environ if environ is not None else os.environ
    return [name for name in LEGACY_SECRET_ENV if env.get(name)]


@dataclass(frozen=True)
class ResolvedSecret:
    """A resolved secret plus metadata safe to display or log."""

    name: str
    value: str | None
    source: str

    @property
    def is_set(self) -> bool:
        return bool(self.value)

    @property
    def masked(self) -> str:
        """A description that reveals nothing but presence and length."""
        if not self.value:
            return "(not set)"
        return f"(set, {len(self.value)} chars)"

    def prefix_check(self) -> tuple[bool, str | None]:
        """Check the value against the provider's public prefix.

        Returns ``(ok, warning)``. The warning names only public prefixes, never
        any character of the key itself.
        """
        expected = EXPECTED_PREFIX.get(self.name)
        if not self.value or not expected:
            return True, None
        if self.value.startswith(expected):
            return True, None
        detected = detect_prefix(self.value)
        return False, (
            f"{self.name}: expected provider prefix '{expected}' but detected "
            f"'{detected or 'unknown'}'; this key may belong to a different provider"
        )


class SecretStore:
    """Resolve secrets from the credential manager, ``.env`` or the environment."""

    def __init__(
        self,
        *,
        backend: KeyringBackend | None = None,
        use_keyring: bool = True,
        service: str = SERVICE_NAME,
        dotenv_path: Path | None = None,
        environ: dict[str, str] | os._Environ[str] | None = None,
    ) -> None:
        self._service = service
        self._dotenv_path = Path(dotenv_path) if dotenv_path is not None else None
        self._environ = environ if environ is not None else os.environ
        self._dotenv_cache: dict[str, str] | None = None

        self._backend: KeyringBackend | None = backend
        if self._backend is None and use_keyring:
            try:
                import keyring

                self._backend = cast(KeyringBackend, keyring)
            except Exception:  # pragma: no cover - depends on host
                self._backend = None

    @property
    def keyring_available(self) -> bool:
        return self._backend is not None

    # -- sources -----------------------------------------------------------
    def _dotenv_values(self) -> dict[str, str]:
        if self._dotenv_cache is None:
            file = self._dotenv_path if self._dotenv_path is not None else find_project_dotenv()
            values: dict[str, str] = {}
            if file is not None and file.is_file():
                try:
                    values = {k: v for k, v in dotenv_values(file).items() if v is not None}
                except Exception:  # pragma: no cover - malformed file should not crash
                    values = {}
            self._dotenv_cache = values
        return self._dotenv_cache

    # -- public API --------------------------------------------------------
    def resolve(self, name: str) -> ResolvedSecret:
        """Resolve ``name`` using the documented priority order."""
        value: str | None = None
        source = SOURCE_NONE

        if self._backend is not None:
            try:
                value = self._backend.get_password(self._service, name)
            except Exception:
                value = None
            if value:
                source = SOURCE_KEYRING

        if not value:
            value = self._dotenv_values().get(name)
            if value:
                source = SOURCE_DOTENV

        if not value:
            value = self._environ.get(name) or None
            if value:
                source = SOURCE_ENV

        if value:
            register_secret(value)
        return ResolvedSecret(name=name, value=value, source=source)

    def get(self, name: str) -> str | None:
        """Return the secret value, or ``None`` if unset."""
        return self.resolve(name).value

    def source(self, name: str) -> str:
        return self.resolve(name).source

    def has(self, name: str) -> bool:
        return self.resolve(name).is_set

    def masked(self, name: str) -> str:
        return self.resolve(name).masked

    def set(self, name: str, value: str) -> None:
        """Persist a secret to the credential manager."""
        if not value:
            raise SecretError("refusing to store an empty secret")
        if self._backend is None:
            raise SecretError("no credential-manager backend available")
        try:
            self._backend.set_password(self._service, name, value)
        except Exception as exc:
            raise SecretError(f"could not store secret {name}: {exc}") from exc
        register_secret(value)

    def delete(self, name: str) -> None:
        """Remove a stored secret, tolerating "not found"."""
        if self._backend is None:
            raise SecretError("no credential-manager backend available")
        try:
            self._backend.delete_password(self._service, name)
        except Exception as exc:
            message = str(exc).lower()
            if "not found" not in message and "no such" not in message:
                raise SecretError(f"could not delete secret {name}: {exc}") from exc
