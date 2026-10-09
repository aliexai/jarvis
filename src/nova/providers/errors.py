"""Typed provider errors and a classifier that turns SDK/transport failures into
friendly, actionable messages.

The UI never sees a stack trace: it receives a ``kind`` and a human ``friendly``
sentence, while the full detail goes to the log (redacted).
"""

from __future__ import annotations

from nova.errors import NovaError


class ProviderError(NovaError):
    """Base class for provider failures."""

    kind = "unknown"
    friendly = "The AI service could not be reached. Please try again."

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


class AuthError(ProviderError):
    kind = "auth"
    friendly = "The API key was rejected. Check NOVA_GEMINI_API_KEY in Settings and try again."


class RateLimitError(ProviderError):
    kind = "rate_limit"
    friendly = "Rate limit reached. Retrying shortly."

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message, retryable=retryable)


class QuotaError(ProviderError):
    kind = "quota"
    friendly = (
        "The free quota for this model is exhausted. Try again later, or switch to a "
        "different model in Settings."
    )


class NetworkError(ProviderError):
    kind = "network"
    friendly = "No connection to the AI service. Check your network or proxy setting."


class ProviderTimeout(ProviderError):
    kind = "timeout"
    friendly = "The AI service took too long to respond. Please try again."

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message, retryable=retryable)


class ModelUnavailableError(ProviderError):
    kind = "model"
    friendly = "That model is not available for this key. Pick another model in Settings."


class SafetyBlockError(ProviderError):
    kind = "safety"
    friendly = "The response was blocked by the provider's safety filters."


class InvalidRequestError(ProviderError):
    kind = "invalid_request"
    friendly = "The request was rejected as invalid. This is a bug in NOVA, not your input."


class JsonSchemaError(ProviderError):
    kind = "json"
    friendly = "The model returned malformed structured data."


_QUOTA_HINTS = ("quota", "billing", "exceeded your current")
_RATE_HINTS = ("rate limit", "too many requests", "resource_exhausted")
_AUTH_HINTS = ("api key not valid", "api_key_invalid", "permission denied", "unauthenticated")


def classify(exc: BaseException) -> ProviderError:
    """Map any raised exception to a :class:`ProviderError`."""
    if isinstance(exc, ProviderError):
        return exc

    message = str(getattr(exc, "message", "") or exc)
    lowered = message.lower()
    code = getattr(exc, "code", None)

    # Transport-level failures come from httpx.
    name = type(exc).__name__
    if "Timeout" in name:
        return ProviderTimeout(f"{name}: {message}")
    if name in {"ConnectError", "TransportError", "ReadError", "WriteError", "RemoteProtocolError"}:
        return NetworkError(f"{name}: {message}")
    if isinstance(exc, (ConnectionError, OSError)) and not isinstance(exc, (ValueError,)):
        return NetworkError(f"{name}: {message}")

    if isinstance(code, int):
        if code in (401, 403):
            return AuthError(message)
        if code == 404:
            return ModelUnavailableError(message)
        if code == 408:
            return ProviderTimeout(message)
        if code == 429:
            if any(hint in lowered for hint in _QUOTA_HINTS):
                return QuotaError(message)
            return RateLimitError(message)
        if code in (400, 422):
            if any(hint in lowered for hint in _AUTH_HINTS):
                return AuthError(message)
            return InvalidRequestError(message)
        if code >= 500:
            return ModelUnavailableError(message)

    if any(hint in lowered for hint in _AUTH_HINTS):
        return AuthError(message)
    if "safety" in lowered or "blocked" in lowered:
        return SafetyBlockError(message)
    if "not found" in lowered and "model" in lowered:
        return ModelUnavailableError(message)

    return ProviderError(f"{name}: {message}")
