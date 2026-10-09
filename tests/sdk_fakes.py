"""Fakes for the google-genai SDK surface that NOVA uses.

Mirrors the shapes the provider reads: ``chunk.text``, ``chunk.candidates[].content.parts[]``
with ``function_call``, ``chunk.usage_metadata``, and ``finish_reason``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeUsage:
    prompt_token_count: int = 0
    response_token_count: int = 0
    thoughts_token_count: int = 0
    total_token_count: int = 0


@dataclass
class FakeFunctionCall:
    name: str
    args: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass
class FakePart:
    text: str | None = None
    function_call: FakeFunctionCall | None = None


@dataclass
class FakeContent:
    parts: list[FakePart] = field(default_factory=list)


@dataclass
class FakeFinishReason:
    name: str


@dataclass
class FakeCandidate:
    content: FakeContent | None = None
    finish_reason: FakeFinishReason | None = None


@dataclass
class FakeChunk:
    text: str | None = None
    candidates: list[FakeCandidate] = field(default_factory=list)
    usage_metadata: FakeUsage | None = None


class FakeAPIError(Exception):
    """Stands in for google.genai.errors.APIError."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class FakeTimeoutError(Exception):
    """Any exception whose name contains 'Timeout' maps to a timeout error."""


class FakeAioModels:
    """Configurable fake for ``client.aio.models``.

    * ``error``            - raise this on every stream call
    * ``transient`` + ``fail_times`` - raise ``transient`` N times, then succeed
    * ``error_after``      - yield N chunks, then raise ``error`` mid-stream
    """

    def __init__(
        self,
        *,
        chunks: list[FakeChunk] | None = None,
        error: BaseException | None = None,
        transient: BaseException | None = None,
        fail_times: int = 0,
        error_after: int | None = None,
        single: FakeChunk | None = None,
        single_error: BaseException | None = None,
    ) -> None:
        self._chunks = chunks or []
        self._error = error
        self._transient = transient
        self._fail_times = fail_times
        self._error_after = error_after
        self._single = single
        self._single_error = single_error
        self.stream_calls = 0
        self.single_calls = 0

    async def generate_content_stream(self, *, model, contents, config):
        self.stream_calls += 1
        if self._fail_times > 0:
            self._fail_times -= 1
            raise self._transient or RuntimeError("simulated transient failure")
        # A mid-stream error must not fire before the generator is returned.
        if self._error is not None and self._error_after is None:
            raise self._error

        chunks = self._chunks
        error = self._error
        error_after = self._error_after

        async def generator():
            for index, chunk in enumerate(chunks):
                if error_after is not None and index == error_after:
                    raise error or RuntimeError("simulated mid-stream failure")
                yield chunk
            if error_after is not None and error_after >= len(chunks):
                raise error or RuntimeError("simulated mid-stream failure")

        return generator()

    async def generate_content(self, *, model, contents, config):
        self.single_calls += 1
        if self._single_error is not None:
            raise self._single_error
        return self._single if self._single is not None else FakeChunk(text="pong")


class FakeAio:
    def __init__(self, models: FakeAioModels) -> None:
        self.models = models

    async def aclose(self) -> None:
        return None


class FakeGenaiClient:
    """A minimal stand-in for ``google.genai.Client``."""

    def __init__(self, **kwargs: Any) -> None:
        self.models = FakeAioModels(**kwargs)
        self.aio = FakeAio(self.models)
        self.closed = False

    def close(self) -> None:
        self.closed = True


def text_chunk(
    text: str, *, usage: FakeUsage | None = None, finish: str | None = None
) -> FakeChunk:
    candidate = FakeCandidate(finish_reason=FakeFinishReason(finish) if finish else None)
    return FakeChunk(text=text, candidates=[candidate], usage_metadata=usage)


def tool_chunk(name: str, args: dict[str, Any], *, finish: str | None = None) -> FakeChunk:
    part = FakePart(function_call=FakeFunctionCall(name=name, args=args))
    candidate = FakeCandidate(
        content=FakeContent(parts=[part]),
        finish_reason=FakeFinishReason(finish) if finish else None,
    )
    return FakeChunk(candidates=[candidate])
