"""A deterministic in-process provider.

Kept permanently (not only for tests): it lets the UI and the chat pipeline be
exercised with no network, no key and no cost.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence

from nova.providers.base import (
    Completion,
    ConnectionResult,
    LLMProvider,
    LLMRequest,
    StreamChunk,
    ToolCall,
    Usage,
)

_CODE_REPLY = """Here's a small, well-typed helper that does exactly that:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    sensor: str
    value: float


def average(readings: list[Reading]) -> float:
    if not readings:
        raise ValueError("no readings supplied")
    return sum(r.value for r in readings) / len(readings)
```

A few things to note:

- The function is **pure**, so it is trivial to test.
- It fails loudly on empty input rather than returning a misleading `0.0`.
- `Reading` is frozen, so a value can never be mutated by accident.
"""

_GENERAL_REPLY = """Good question. Here's how I'd approach **"{prompt}"**:

1. Restate the goal and the constraints so we agree on the target.
2. Break it into small, independently verifiable steps.
3. Do the smallest useful slice first, then iterate.

Tell me which step you want to start with and I'll dig in."""

_SUMMARY_REPLY = """Here's a summary:

- **Status:** all checks passing.
- **Changed:** `nova/providers/` and the chat pipeline.
- **Next:** wire the tools panel."""

_TOOL_FOLLOWUP = "Done — the tool result above is the current value."


# Phrases that make the mock suggest a demo tool, so tool calling can be shown
# with no key configured. Deliberately avoids "what time is it", which is
# answered locally without reaching any provider.
_TOOL_TRIGGERS: tuple[tuple[str, str], ...] = (
    ("get_time", "get_time"),
    ("timestamp", "get_time"),
    ("wall clock", "get_time"),
    ("get_system_info", "get_system_info"),
    ("system info", "get_system_info"),
    ("specs", "get_system_info"),
    ("echo", "echo"),
)


def reply_for(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("code", "python", "function", "script", "test")):
        return _CODE_REPLY
    if any(word in lowered for word in ("summary", "summarise", "summarize", "status", "report")):
        return _SUMMARY_REPLY
    return _GENERAL_REPLY.format(prompt=text.strip()[:80])


def chunk_text(text: str, words_per_chunk: int = 3) -> list[str]:
    words = text.split(" ")
    chunks: list[str] = []
    for index in range(0, len(words), words_per_chunk):
        group = words[index : index + words_per_chunk]
        is_last = index + words_per_chunk >= len(words)
        chunks.append(" ".join(group) if is_last else " ".join(group) + " ")
    return chunks


class MockProvider(LLMProvider):
    """Streams canned text with a simulated token count."""

    name = "mock"

    def __init__(
        self,
        *,
        reply: str | None = None,
        delay: float = 0.0,
        words_per_chunk: int = 3,
        tool_calls: Sequence[ToolCall] | None = None,
        tool_call_rounds: int = 1,
        fail_with: BaseException | None = None,
    ) -> None:
        self._reply = reply
        self._delay = delay
        self._words_per_chunk = words_per_chunk
        self._tool_calls = list(tool_calls or [])
        self._tool_call_rounds = tool_call_rounds
        self._stream_calls = 0
        self._emitted_tools = False
        self._fail_with = fail_with

    def _text_for(self, request: LLMRequest) -> str:
        # The round after a tool call just confirms the result, rather than
        # repeating the whole reply.
        if self._emitted_tools:
            return _TOOL_FOLLOWUP
        if self._reply is not None:
            return self._reply
        last_user = next((m.text for m in reversed(request.messages) if m.role == "user"), "")
        return reply_for(last_user)

    def _implicit_tool_calls(self, request: LLMRequest) -> list[ToolCall]:
        """Suggest a demo tool when the prompt names one, so tool calling can be
        demonstrated with no key. Explicit ``tool_calls`` always win."""
        if self._tool_calls:
            return []
        last_user = next((m.text for m in reversed(request.messages) if m.role == "user"), "")
        lowered = last_user.lower()
        for needle, name in _TOOL_TRIGGERS:
            if needle not in lowered:
                continue
            if name == "echo":
                return [ToolCall("echo", {"text": last_user[:60] or "hello"})]
            return [ToolCall(name, {})]
        return []

    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        if self._fail_with is not None:
            raise self._fail_with

        self._stream_calls += 1
        text = self._text_for(request)
        pieces = chunk_text(text, self._words_per_chunk)
        produced = ""
        for piece in pieces:
            produced += piece
            if self._delay:
                await asyncio.sleep(self._delay)
            yield StreamChunk(text=piece)

        calls: list[ToolCall] = []
        if self._stream_calls <= self._tool_call_rounds:
            calls = list(self._tool_calls) or self._implicit_tool_calls(request)
        self._emitted_tools = bool(calls)
        for call in calls:
            yield StreamChunk(tool_calls=[call])

        yield StreamChunk(
            usage=self._usage_for(request, produced),
            finish_reason="STOP",
        )

    def _usage_for(self, request: LLMRequest, produced: str) -> Usage:
        input_tokens = sum(len(m.text.split()) for m in request.messages) * 2
        output_tokens = len(produced.split()) * 2
        return Usage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
        )

    async def complete(self, request: LLMRequest) -> Completion:
        texts: list[str] = []
        usage = Usage()
        calls: list[ToolCall] = []
        finish: str | None = None
        async for chunk in self.stream(request):
            texts.append(chunk.text)
            calls.extend(chunk.tool_calls)
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.finish_reason:
                finish = chunk.finish_reason
        return Completion("".join(texts), request.model, usage, finish, calls)

    async def test_connection(self, model: str) -> ConnectionResult:
        return ConnectionResult(True, model, 1, "mock provider always replies")
