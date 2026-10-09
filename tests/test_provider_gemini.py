"""Provider tests: the Gemini implementation against a fake SDK.

Covers streaming, tool-call parsing, usage mapping, retries, every mapped error
type, cancellation, and safety blocks.
"""

from __future__ import annotations

import pytest

from nova.providers.base import LLMRequest, Message
from nova.providers.errors import (
    AuthError,
    InvalidRequestError,
    ModelUnavailableError,
    ProviderTimeout,
    QuotaError,
    RateLimitError,
    SafetyBlockError,
)
from nova.providers.gemini import GeminiProvider
from sdk_fakes import (
    FakeAPIError,
    FakeGenaiClient,
    FakeTimeoutError,
    FakeUsage,
    text_chunk,
    tool_chunk,
)


def _provider(client: FakeGenaiClient, **kwargs) -> GeminiProvider:
    return GeminiProvider("test-key", client=client, base_backoff=0.0, max_retries=1, **kwargs)


def _request(text: str = "hi") -> LLMRequest:
    return LLMRequest(model="gemini-test", messages=[Message("user", text)])


# -- streaming -------------------------------------------------------------


async def test_streams_text_and_maps_usage():
    usage = FakeUsage(
        prompt_token_count=10, response_token_count=5, thoughts_token_count=2, total_token_count=17
    )
    client = FakeGenaiClient(
        chunks=[text_chunk("Hel"), text_chunk("lo", usage=usage, finish="STOP")]
    )

    chunks = [chunk async for chunk in _provider(client).stream(_request())]

    assert "".join(chunk.text for chunk in chunks) == "Hello"
    assert chunks[-1].usage is not None
    assert chunks[-1].usage.input_tokens == 10
    # Output is billed including thinking tokens.
    assert chunks[-1].usage.output_tokens == 7
    assert chunks[-1].usage.thoughts_tokens == 2
    assert chunks[-1].finish_reason == "STOP"


async def test_parses_tool_calls():
    client = FakeGenaiClient(chunks=[tool_chunk("get_time", {}), text_chunk("done", finish="STOP")])

    calls = []
    async for chunk in _provider(client).stream(_request()):
        calls.extend(chunk.tool_calls)

    assert [call.name for call in calls] == ["get_time"]
    assert calls[0].args == {}


async def test_complete_aggregates_text_and_usage():
    usage = FakeUsage(prompt_token_count=3, response_token_count=4, total_token_count=7)
    client = FakeGenaiClient(chunks=[text_chunk("a"), text_chunk("b", usage=usage, finish="STOP")])

    completion = await _provider(client).complete(_request())

    assert completion.text == "ab"
    assert completion.model == "gemini-test"
    assert completion.usage.total_tokens == 7


async def test_missing_key_raises_auth_error():
    provider = GeminiProvider("", client=FakeGenaiClient(chunks=[text_chunk("x")]))
    with pytest.raises(AuthError):
        async for _ in provider.stream(_request()):
            pass


# -- error mapping ---------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (401, AuthError),
        (403, AuthError),
        (404, ModelUnavailableError),
        (429, RateLimitError),
        (400, InvalidRequestError),
        (503, ModelUnavailableError),
    ],
)
async def test_maps_status_codes(code, expected):
    client = FakeGenaiClient(error=FakeAPIError(code, "boom"))
    with pytest.raises(expected):
        async for _ in _provider(client).stream(_request()):
            pass


async def test_429_with_quota_language_is_a_quota_error():
    client = FakeGenaiClient(error=FakeAPIError(429, "You exceeded your current quota"))
    with pytest.raises(QuotaError):
        async for _ in _provider(client).stream(_request()):
            pass


async def test_timeout_is_mapped():
    client = FakeGenaiClient(error=FakeTimeoutError("took too long"))
    with pytest.raises(ProviderTimeout):
        async for _ in _provider(client).stream(_request()):
            pass


async def test_safety_finish_raises_on_complete():
    client = FakeGenaiClient(chunks=[text_chunk("", finish="SAFETY")])
    with pytest.raises(SafetyBlockError):
        await _provider(client).complete(_request())


# -- retries ---------------------------------------------------------------


async def test_retries_transient_failures_before_first_byte():
    client = FakeGenaiClient(
        chunks=[text_chunk("recovered", finish="STOP")],
        transient=FakeAPIError(429, "rate limited"),
        fail_times=2,
    )
    provider = GeminiProvider("k", client=client, base_backoff=0.0, max_retries=3)

    chunks = [chunk async for chunk in provider.stream(_request())]

    assert "".join(chunk.text for chunk in chunks) == "recovered"
    assert client.models.stream_calls == 3


async def test_gives_up_after_max_retries():
    client = FakeGenaiClient(transient=FakeAPIError(429, "rate limited"), fail_times=10)
    provider = GeminiProvider("k", client=client, base_backoff=0.0, max_retries=2)

    with pytest.raises(RateLimitError):
        async for _ in provider.stream(_request()):
            pass
    assert client.models.stream_calls == 3  # initial + 2 retries


async def test_does_not_retry_after_the_first_chunk():
    client = FakeGenaiClient(
        chunks=[text_chunk("partial")],
        error=FakeAPIError(500, "server exploded"),
        error_after=1,
    )
    provider = GeminiProvider("k", client=client, base_backoff=0.0, max_retries=3)

    received = ""
    with pytest.raises(ModelUnavailableError):
        async for chunk in provider.stream(_request()):
            received += chunk.text

    assert received == "partial"
    assert client.models.stream_calls == 1


async def test_non_retryable_errors_are_not_retried():
    client = FakeGenaiClient(error=FakeAPIError(401, "bad key"))
    with pytest.raises(AuthError):
        async for _ in _provider(client).stream(_request()):
            pass
    assert client.models.stream_calls == 1


# -- cancellation ----------------------------------------------------------


async def test_stream_can_be_cancelled():
    import asyncio

    client = FakeGenaiClient(chunks=[text_chunk(str(i)) for i in range(50)])
    provider = _provider(client)

    async def consume():
        async for _ in provider.stream(_request()):
            await asyncio.sleep(0)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


# -- connection test -------------------------------------------------------


async def test_connection_reports_success_and_latency():
    client = FakeGenaiClient(single=text_chunk("pong"))
    result = await _provider(client).test_connection("gemini-3.5-flash-lite")

    assert result.ok is True
    assert result.model == "gemini-3.5-flash-lite"
    assert result.latency_ms >= 0


async def test_connection_reports_failure_without_key_material():
    secret = "AIzaSyABCDEFGHIJKLMNOP1234567890"
    client = FakeGenaiClient(single_error=FakeAPIError(401, f"invalid key {secret}"))
    result = await _provider(client).test_connection("gemini-3.5-flash-lite")

    assert result.ok is False
    assert secret not in result.detail
