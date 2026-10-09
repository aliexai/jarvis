"""Exception hierarchy for NOVA.

Every error raised by the core derives from :class:`NovaError` so that the UI
layer can present a friendly message while the full detail stays in the log.
"""

from __future__ import annotations


class NovaError(Exception):
    """Base class for all NOVA errors."""


class ConfigError(NovaError):
    """Raised when settings cannot be loaded, validated or migrated."""


class PolicyError(NovaError):
    """Raised when an action violates the security policy.

    A raised :class:`PolicyError` always means *deny* - the policy engine is
    fail-closed, so any evaluation that raises is treated as a refusal.
    """


class SecretError(NovaError):
    """Raised when a secret cannot be read, written or deleted."""


class ProviderError(NovaError):
    """Raised by LLM / TTS / STT providers."""
