"""Provider-agnostic LLM interface.

The rest of NOVA talks to this, never to a vendor SDK directly, so a second
provider (or a local model) can be added without touching the chat pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["user", "model", "tool"]


@dataclass(frozen=True)
class Message:
    """One turn of conversation.

    ``role="model"`` may carry ``tool_calls`` (the model asking for tools) and
    ``role="tool"`` carries the result of one of those calls back to the model.
    """

    role: Role
    text: str = ""
    tool_name: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    tool_response: dict[str, Any] | None = None


@dataclass(frozen=True)
class ToolSpec:
    """A tool as the provider sees it."""

    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ToolCall:
    """A tool invocation requested by the model."""

    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass
class Usage:
    """Token accounting for a single request."""

    input_tokens: int = 0
    output_tokens: int = 0
    thoughts_tokens: int = 0
    total_tokens: int = 0

    @property
    def has_data(self) -> bool:
        return bool(self.total_tokens or self.input_tokens or self.output_tokens)


@dataclass
class StreamChunk:
    """A piece of a streamed response."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: Usage | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class LLMRequest:
    model: str
    messages: Sequence[Message]
    system_instruction: str | None = None
    tools: Sequence[ToolSpec] = ()
    json_schema: dict[str, Any] | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    usage: Usage
    finish_reason: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass(frozen=True)
class ConnectionResult:
    ok: bool
    model: str
    latency_ms: int
    detail: str


class LLMProvider(ABC):
    """Interface every provider implements."""

    name = "base"

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        """Yield chunks as they arrive."""

    @abstractmethod
    async def complete(self, request: LLMRequest) -> Completion:
        """Return the whole response."""

    @abstractmethod
    async def test_connection(self, model: str) -> ConnectionResult:
        """Send the smallest possible request and report success and latency."""

    async def aclose(self) -> None:
        """Release any held resources."""
        return None
