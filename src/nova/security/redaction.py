"""Secret redaction.

Two layers defend against secret leakage into logs or UI:

1. **Patterns** - regexes for the token shapes we care about (Google API keys,
   ``sk_``/``sk-`` keys, bearer tokens, and ``key=value`` assignments).
2. **Registered literals** - any value returned by the secret store is
   registered here, so even a token with no recognisable shape is scrubbed
   verbatim wherever it appears.

:class:`RedactingFilter` applies both to every log record before it is
formatted, so nothing downstream (file handler, console, diagnostics export)
can emit a raw secret.
"""

from __future__ import annotations

import logging
import re
import threading

REDACTED = "***REDACTED***"

# Token shapes.
_BASE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"AIza[0-9A-Za-z_\-]{10,}"),  # Google API key
    re.compile(r"sk_[0-9A-Za-z]{10,}"),  # ElevenLabs-style
    re.compile(r"sk-[0-9A-Za-z_\-]{10,}"),  # OpenAI-style
    re.compile(r"(?i)bearer\s+[0-9A-Za-z._\-]{8,}"),  # Authorization headers
)

# ``api_key=...`` / ``token: ...`` style assignments (keep the label, drop value).
_KV_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|auth[_-]?token|secret|password|passwd)\b"
    r"(\s*[:=]\s*)(\S+)"
)

_MIN_LITERAL_LENGTH = 6
_literals: set[str] = set()
_lock = threading.Lock()


def register_secret(value: str | None) -> None:
    """Register a literal value to be scrubbed verbatim from all output."""
    if not value or len(value) < _MIN_LITERAL_LENGTH:
        return
    with _lock:
        _literals.add(value)


def forget_secret(value: str | None) -> None:
    """Stop scrubbing a previously registered literal (used in tests)."""
    if not value:
        return
    with _lock:
        _literals.discard(value)


def reset_registered_secrets() -> None:
    """Clear all registered literals (used in tests)."""
    with _lock:
        _literals.clear()


def _patterns() -> list[re.Pattern[str]]:
    with _lock:
        literals = sorted(_literals, key=len, reverse=True)
    # Longest literals first so a full key is replaced before any sub-shape.
    return [re.compile(re.escape(lit)) for lit in literals] + list(_BASE_PATTERNS)


def redact_text(text: str | None) -> str | None:
    """Return ``text`` with every recognised secret replaced by ``REDACTED``."""
    if not text:
        return text
    result = text
    for pattern in _patterns():
        result = pattern.sub(REDACTED, result)
    result = _KV_PATTERN.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", result)
    return result


def _scrub(value: object) -> object:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, tuple):
        return tuple(_scrub(item) for item in value)
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items()}
    return value


class RedactingFilter(logging.Filter):
    """Logging filter that scrubs the message template and its arguments."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if record.args:
            record.args = _scrub(record.args)  # type: ignore[assignment]
        return True
