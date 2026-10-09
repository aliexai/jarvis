"""Structured (JSON mode) output tests."""

from __future__ import annotations

import pytest

from nova.providers.base import Completion, LLMProvider, LLMRequest, Usage
from nova.providers.errors import JsonSchemaError
from nova.providers.mock import MockProvider
from nova.providers.structured import extract_json, generate_json

SCHEMA = {
    "type": "object",
    "properties": {"name": {"type": "string"}},
    "required": ["name"],
    "additionalProperties": False,
}


class ScriptedProvider(MockProvider):
    """Returns a different canned reply on each call."""

    def __init__(self, replies: list[str]) -> None:
        super().__init__()
        self._replies = replies
        self.calls = 0

    def _text_for(self, request: LLMRequest) -> str:
        index = min(self.calls, len(self._replies) - 1)
        self.calls += 1
        return self._replies[index]


class RecordingProvider(LLMProvider):
    name = "recording"

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.requests: list[LLMRequest] = []

    async def stream(self, request):  # pragma: no cover - unused
        yield

    async def complete(self, request: LLMRequest) -> Completion:
        self.requests.append(request)
        return Completion(self.reply, request.model, Usage(1, 1, total_tokens=2))

    async def test_connection(self, model):  # pragma: no cover - unused
        raise NotImplementedError


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_from_code_fence():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('```\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_invalid():
    assert extract_json("not json at all") is None
    assert extract_json("") is None


async def test_generate_json_returns_valid_object():
    provider = MockProvider(reply='{"name": "nova"}')
    assert await generate_json(provider, model="m", prompt="give me a name", schema=SCHEMA) == {
        "name": "nova"
    }


async def test_generate_json_retries_then_succeeds():
    provider = ScriptedProvider(["not json", '{"name": "nova"}'])
    result = await generate_json(
        provider, model="m", prompt="give me a name", schema=SCHEMA, retries=1
    )
    assert result == {"name": "nova"}
    assert provider.calls == 2


async def test_generate_json_retries_on_schema_mismatch():
    provider = ScriptedProvider(['{"wrong": true}', '{"name": "nova"}'])
    result = await generate_json(
        provider, model="m", prompt="give me a name", schema=SCHEMA, retries=1
    )
    assert result == {"name": "nova"}


async def test_generate_json_raises_after_retries_exhausted():
    provider = ScriptedProvider(["nope"])
    with pytest.raises(JsonSchemaError):
        await generate_json(provider, model="m", prompt="x", schema=SCHEMA, retries=1)
    assert provider.calls == 2


async def test_generate_json_asks_for_json_mode():
    provider = RecordingProvider('{"name": "nova"}')
    await generate_json(provider, model="m", prompt="x", schema=SCHEMA)
    assert provider.requests[0].json_schema == SCHEMA
    assert provider.requests[0].temperature == 0.0
