"""Tests for secret redaction."""

from __future__ import annotations

import logging

from nova.security.redaction import (
    REDACTED,
    RedactingFilter,
    redact_text,
    register_secret,
)


def test_google_api_key_shape_is_redacted():
    text = "auth failed for AIzaSyABCDEFGHIJKLMNOP1234567890abcdef"
    out = redact_text(text)
    assert "AIzaSy" not in out
    assert REDACTED in out


def test_elevenlabs_key_shape_is_redacted():
    key = "sk_abcdef0123456789abcdef0123456789abcd"
    out = redact_text(f"using {key}")
    assert "abcdef0123" not in out
    assert REDACTED in out


def test_key_value_assignment_keeps_label():
    out = redact_text('api_key="abc123secret"')
    assert out.startswith("api_key=")
    assert "abc123secret" not in out
    assert REDACTED in out


def test_registered_literal_is_scrubbed_verbatim():
    secret = "opaque-value-1234567890"
    register_secret(secret)
    assert redact_text(f"token={secret} end") == f"token={REDACTED} end"


def test_short_literals_are_not_registered():
    register_secret("abc")
    assert redact_text("abc def") == "abc def"


def test_filter_scrubs_message_and_args():
    secret = "abcdef1234567890"
    register_secret(secret)
    record = logging.LogRecord(
        name="nova.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="value is %s",
        args=(secret,),
        exc_info=None,
    )
    assert RedactingFilter().filter(record) is True
    assert secret not in record.getMessage()
    assert REDACTED in record.getMessage()


def test_filter_scrubs_dict_args():
    secret = "abcdef1234567890"
    register_secret(secret)
    record = logging.LogRecord(
        name="nova.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="%(key)s",
        args=({"key": secret},),
        exc_info=None,
    )
    RedactingFilter().filter(record)
    assert secret not in record.getMessage()
