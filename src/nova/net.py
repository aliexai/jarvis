"""Network and proxy handling.

This machine has a Windows system proxy configured as ``socks4://[::1]:9050``.
httpx (used by the Google SDK) cannot even *construct* a client with that scheme
- it raises ``ValueError: Unknown scheme for proxy URL`` - so NOVA must decide
explicitly what to do rather than inheriting it.

Behaviour, configurable in Settings:

* ``bypass`` (default) - ignore every proxy. The Windows setting is left alone.
* ``system``           - use the system proxy, but only if its scheme is one
  httpx supports (http/https). A SOCKS proxy is reported and bypassed.
* ``manual``           - use the URL given in Settings.

We never write to the Windows proxy configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_SUPPORTED_SCHEMES = ("http://", "https://")
PROXY_MODES = ("bypass", "system", "manual")


def detect_system_proxies() -> dict[str, str]:
    """Read the configured proxies (environment + Windows registry). Read-only."""
    try:
        from urllib.request import getproxies

        return {str(k): str(v) for k, v in getproxies().items()}
    except Exception:  # pragma: no cover - defensive
        return {}


def _first_supported(proxies: dict[str, str]) -> str | None:
    for key in ("https", "http"):
        value = proxies.get(key)
        if value and value.lower().startswith(_SUPPORTED_SCHEMES):
            return value
    return None


@dataclass(frozen=True)
class ProxyDecision:
    mode: str
    detected: dict[str, str] = field(default_factory=dict)
    effective_url: str | None = None
    supported: bool = True
    note: str = ""

    @property
    def bypassing(self) -> bool:
        return self.effective_url is None


def resolve_proxy(mode: str, manual_url: str | None = None) -> ProxyDecision:
    """Decide which proxy, if any, the SDK should use."""
    mode = mode if mode in PROXY_MODES else "bypass"
    proxies = detect_system_proxies()

    if mode == "bypass":
        return ProxyDecision(mode, proxies, None, True, "bypassing all proxies")

    if mode == "manual":
        url = (manual_url or "").strip()
        if not url:
            return ProxyDecision(mode, proxies, None, True, "no manual proxy set; bypassing")
        if url.lower().startswith(_SUPPORTED_SCHEMES):
            return ProxyDecision(mode, proxies, url, True, "using the manual proxy")
        return ProxyDecision(
            mode, proxies, None, False, "the manual proxy scheme is not supported; bypassing"
        )

    # system
    chosen = _first_supported(proxies)
    if chosen:
        return ProxyDecision(mode, proxies, chosen, True, "using the system http(s) proxy")
    if proxies:
        return ProxyDecision(
            mode,
            proxies,
            None,
            False,
            "the system proxy uses an unsupported scheme (SOCKS); bypassing it",
        )
    return ProxyDecision(mode, proxies, None, True, "no system proxy detected")


def build_http_options(
    decision: ProxyDecision, *, timeout_seconds: float, retry_attempts: int = 0
) -> Any:
    """Build ``google.genai.types.HttpOptions`` for the resolved proxy decision.

    ``trust_env`` is always disabled so the Windows registry proxy can never leak
    in through httpx's environment handling.
    """
    from google.genai import types

    client_args: dict[str, Any] = {"trust_env": False}
    if decision.effective_url:
        client_args["proxy"] = decision.effective_url

    retry = types.HttpRetryOptions(attempts=retry_attempts) if retry_attempts else None
    return types.HttpOptions(
        timeout=int(timeout_seconds * 1000),
        client_args=client_args,
        async_client_args=dict(client_args),
        retry_options=retry,
    )
