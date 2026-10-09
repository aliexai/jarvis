"""Integration tests proving log files redact secrets."""

from __future__ import annotations

from nova.config.paths import get_paths
from nova.logging_setup import setup_logging, shutdown_logging
from nova.security.redaction import REDACTED, register_secret


def _portable_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_DIR", str(tmp_path))
    monkeypatch.delenv("NOVA_CONFIG_FILE", raising=False)
    return get_paths(portable=True)


def test_log_file_redacts_registered_secret(tmp_path, monkeypatch):
    paths = _portable_paths(tmp_path, monkeypatch)
    secret = "sk_live_abcdef1234567890"
    register_secret(secret)

    logger = setup_logging(paths, console=False)
    try:
        logger.info("calling provider with key %s", secret)
    finally:
        shutdown_logging()

    content = paths.log_file.read_text(encoding="utf-8")
    assert secret not in content
    assert REDACTED in content


def test_log_file_redacts_pattern_shaped_key(tmp_path, monkeypatch):
    paths = _portable_paths(tmp_path, monkeypatch)
    key = "AIzaSyABCDEFGHIJKLMNOP1234567890"

    logger = setup_logging(paths, console=False)
    try:
        logger.warning("auth failed for %s", key)
    finally:
        shutdown_logging()

    content = paths.log_file.read_text(encoding="utf-8")
    assert key not in content
    assert REDACTED in content
