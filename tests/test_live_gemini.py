"""One small live test against the real Gemini API.

Skipped unless NOVA_GEMINI_API_KEY resolves (keyring, .env or environment). It
sends a single one-line prompt with a tiny token cap.
"""

from __future__ import annotations

import pytest

from nova.net import resolve_proxy
from nova.providers.base import LLMRequest, Message
from nova.providers.gemini import GeminiProvider
from nova.security.secrets import GEMINI_API_KEY, SecretStore

# Resolved at import time, before the per-test environment isolation runs.
_KEY = SecretStore().get(GEMINI_API_KEY)

pytestmark = pytest.mark.skipif(
    not _KEY, reason="NOVA_GEMINI_API_KEY is not set; live test skipped"
)

LIVE_MODEL = "gemini-3.5-flash-lite"


async def test_live_one_line_prompt():
    assert _KEY  # narrowed by the skipif
    provider = GeminiProvider(_KEY, proxy=resolve_proxy("bypass"), timeout_seconds=45)

    try:
        result = await provider.test_connection(LIVE_MODEL)
        assert result.ok, f"connection failed: {result.detail}"

        completion = await provider.complete(
            LLMRequest(
                model=LIVE_MODEL,
                messages=[Message("user", "Reply with the single word: ready")],
                max_output_tokens=16,
            )
        )
        assert completion.text.strip()
        # Token accounting must come back from the service.
        assert completion.usage.total_tokens > 0
    finally:
        await provider.aclose()
