"""Proxy detection and SDK client construction tests.

The regression that matters: this machine's Windows SOCKS proxy used to make
``google.genai.Client(...)`` raise ``ValueError: Unknown scheme for proxy URL``.
"""

from __future__ import annotations

import pytest

import nova.net as net
from nova.net import build_http_options, resolve_proxy


def test_bypass_ignores_every_detected_proxy(monkeypatch):
    monkeypatch.setattr(net, "detect_system_proxies", lambda: {"https": "socks4://[::1]:9050"})
    decision = resolve_proxy("bypass")
    assert decision.bypassing is True
    assert decision.effective_url is None


def test_system_socks_proxy_is_reported_and_bypassed(monkeypatch):
    monkeypatch.setattr(
        net,
        "detect_system_proxies",
        lambda: {"socks": "socks://[::1]:9050", "https": "socks4://[::1]:9050"},
    )
    decision = resolve_proxy("system")
    assert decision.supported is False
    assert decision.effective_url is None
    assert "SOCKS" in decision.note


def test_system_http_proxy_is_used(monkeypatch):
    monkeypatch.setattr(net, "detect_system_proxies", lambda: {"https": "http://127.0.0.1:8080"})
    decision = resolve_proxy("system")
    assert decision.effective_url == "http://127.0.0.1:8080"
    assert decision.supported is True


def test_manual_proxy_is_used():
    decision = resolve_proxy("manual", "http://127.0.0.1:3128")
    assert decision.effective_url == "http://127.0.0.1:3128"


def test_manual_unsupported_scheme_is_bypassed():
    decision = resolve_proxy("manual", "ftp://nope")
    assert decision.effective_url is None
    assert decision.supported is False


def test_manual_without_url_is_bypassed():
    assert resolve_proxy("manual", "").bypassing is True


def test_unknown_mode_falls_back_to_bypass():
    assert resolve_proxy("nonsense").mode == "bypass"


def test_http_options_disable_trust_env():
    options = build_http_options(resolve_proxy("bypass"), timeout_seconds=5.0)
    assert options.client_args["trust_env"] is False
    assert options.async_client_args["trust_env"] is False


def test_http_options_pass_an_explicit_proxy():
    options = build_http_options(
        resolve_proxy("manual", "http://127.0.0.1:3128"), timeout_seconds=5.0
    )
    assert options.client_args["proxy"] == "http://127.0.0.1:3128"


def test_gemini_client_builds_even_with_a_socks_system_proxy(monkeypatch):
    """Regression test for the proxy crash on this machine."""
    pytest.importorskip("google.genai")
    monkeypatch.setattr(net, "detect_system_proxies", lambda: {"https": "socks4://[::1]:9050"})

    from nova.providers.gemini import GeminiProvider

    provider = GeminiProvider("dummy-key", proxy=resolve_proxy("bypass"))
    assert provider is not None


def test_gemini_client_builds_in_system_mode_with_socks(monkeypatch):
    pytest.importorskip("google.genai")
    monkeypatch.setattr(net, "detect_system_proxies", lambda: {"https": "socks4://[::1]:9050"})

    from nova.providers.gemini import GeminiProvider

    provider = GeminiProvider("dummy-key", proxy=resolve_proxy("system"))
    assert provider is not None
