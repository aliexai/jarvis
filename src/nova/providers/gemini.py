"""Gemini implementation of the provider interface (google-genai >= 2, < 3).

Notes on the SDK surface this targets (google-genai 2.29):

* ``client.aio.models.generate_content_stream`` returns an async iterator.
* Token counts live on ``usage_metadata`` as ``prompt_token_count`` and
  ``response_token_count`` (plus ``thoughts_token_count``).
* Errors raised by the service are ``google.genai.errors.APIError`` with a
  numeric ``code``.

The SDK client is injectable so tests can run against a fake SDK.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import AsyncIterator, Sequence
from typing import Any

from nova.logging_setup import get_logger
from nova.net import ProxyDecision, build_http_options
from nova.providers.base import (
    Completion,
    ConnectionResult,
    LLMProvider,
    LLMRequest,
    Message,
    StreamChunk,
    ToolCall,
    ToolSpec,
    Usage,
)
from nova.providers.errors import (
    AuthError,
    ProviderError,
    SafetyBlockError,
    classify,
)
from nova.security.redaction import redact_text

MAX_BACKOFF_SECONDS = 8.0


class GeminiProvider(LLMProvider):
    """Streams and completes text with Google Gemini."""

    name = "gemini"

    def __init__(
        self,
        api_key: str | None,
        *,
        proxy: ProxyDecision | None = None,
        timeout_seconds: float = 60.0,
        max_retries: int = 3,
        base_backoff: float = 0.5,
        client: Any | None = None,
    ) -> None:
        self._api_key = api_key or ""
        self._max_retries = max(0, max_retries)
        self._base_backoff = base_backoff
        self._log = get_logger("provider.gemini")
        self._client = client if client is not None else self._build_client(proxy, timeout_seconds)

    # -- construction ------------------------------------------------------
    def _build_client(self, proxy: ProxyDecision | None, timeout_seconds: float) -> Any:
        from google import genai

        decision = proxy
        http_options = (
            build_http_options(
                decision, timeout_seconds=timeout_seconds, retry_attempts=self._max_retries
            )
            if decision is not None
            else None
        )
        return genai.Client(api_key=self._api_key or None, http_options=http_options)

    def _require_key(self) -> None:
        if not self._api_key:
            raise AuthError("no API key configured")

    # -- request building --------------------------------------------------
    @staticmethod
    def _to_contents(messages: Sequence[Message]) -> list[Any]:
        from google.genai import types

        contents: list[Any] = []
        for message in messages:
            if message.role == "tool":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[
                            types.Part(
                                function_response=types.FunctionResponse(
                                    name=message.tool_name or "tool",
                                    response=message.tool_response or {"result": message.text},
                                )
                            )
                        ],
                    )
                )
                continue

            if message.role == "model" and message.tool_calls:
                parts: list[Any] = []
                if message.text:
                    parts.append(types.Part(text=message.text))
                parts.extend(
                    types.Part(function_call=types.FunctionCall(name=call.name, args=call.args))
                    for call in message.tool_calls
                )
                contents.append(types.Content(role="model", parts=parts))
                continue

            role = "user" if message.role == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=message.text)]))
        return contents

    @staticmethod
    def _to_tools(tools: Sequence[ToolSpec]) -> list[Any] | None:
        if not tools:
            return None
        from google.genai import types

        declarations = [
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description,
                parameters_json_schema=tool.parameters,
            )
            for tool in tools
        ]
        return [types.Tool(function_declarations=declarations)]

    def _build_config(self, request: LLMRequest) -> Any:
        from google.genai import types

        kwargs: dict[str, Any] = {}
        if request.system_instruction:
            kwargs["system_instruction"] = request.system_instruction
        tools = self._to_tools(request.tools)
        if tools:
            kwargs["tools"] = tools
        if request.json_schema:
            kwargs["response_mime_type"] = "application/json"
            kwargs["response_json_schema"] = request.json_schema
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            kwargs["max_output_tokens"] = request.max_output_tokens
        return types.GenerateContentConfig(**kwargs)

    # -- response parsing --------------------------------------------------
    @staticmethod
    def _usage_from(metadata: Any) -> Usage | None:
        if metadata is None:
            return None
        prompt = int(getattr(metadata, "prompt_token_count", 0) or 0)
        response = int(getattr(metadata, "response_token_count", 0) or 0)
        thoughts = int(getattr(metadata, "thoughts_token_count", 0) or 0)
        total = int(getattr(metadata, "total_token_count", 0) or 0)
        # The pricing page bills output "including thinking tokens".
        output = response + thoughts
        return Usage(
            input_tokens=prompt,
            output_tokens=output,
            thoughts_tokens=thoughts,
            total_tokens=total or (prompt + output),
        )

    @staticmethod
    def _finish_name(reason: Any) -> str | None:
        if reason is None:
            return None
        name = getattr(reason, "name", None)
        if name:
            return str(name)
        text = str(reason)
        return text.split(".")[-1] if text else None

    def _parse_chunk(self, chunk: Any) -> StreamChunk:
        text = ""
        try:
            text = chunk.text or ""
        except Exception:
            text = ""

        calls: list[ToolCall] = []
        finish: str | None = None
        for candidate in getattr(chunk, "candidates", None) or []:
            finish = self._finish_name(getattr(candidate, "finish_reason", None)) or finish
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                call = getattr(part, "function_call", None)
                if call is not None:
                    calls.append(
                        ToolCall(
                            name=str(call.name),
                            args=dict(call.args or {}),
                            id=getattr(call, "id", None),
                        )
                    )
        return StreamChunk(
            text=text,
            tool_calls=calls,
            usage=self._usage_from(getattr(chunk, "usage_metadata", None)),
            finish_reason=finish,
        )

    # -- provider interface ------------------------------------------------
    async def stream(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        self._require_key()
        attempt = 0
        while True:
            produced_any = False
            try:
                async for chunk in self._stream_once(request):
                    produced_any = True
                    yield chunk
                return
            except ProviderError:
                raise
            except Exception as exc:
                error = classify(exc)
                if produced_any or not error.retryable or attempt >= self._max_retries:
                    raise error from exc
                attempt += 1
                delay = min(self._base_backoff * 2 ** (attempt - 1), MAX_BACKOFF_SECONDS)
                self._log.warning(
                    "stream failed (%s), retry %s/%s in %.1fs",
                    error.kind,
                    attempt,
                    self._max_retries,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _stream_once(self, request: LLMRequest) -> AsyncIterator[StreamChunk]:
        stream = await self._client.aio.models.generate_content_stream(
            model=request.model,
            contents=self._to_contents(request.messages),
            config=self._build_config(request),
        )
        async for chunk in stream:
            yield self._parse_chunk(chunk)

    async def complete(self, request: LLMRequest) -> Completion:
        texts: list[str] = []
        calls: list[ToolCall] = []
        usage = Usage()
        finish: str | None = None

        async for chunk in self.stream(request):
            if chunk.text:
                texts.append(chunk.text)
            calls.extend(chunk.tool_calls)
            if chunk.usage is not None:
                usage = chunk.usage
            if chunk.finish_reason:
                finish = chunk.finish_reason

        if finish == "SAFETY":
            raise SafetyBlockError("response blocked by safety filters")
        return Completion(
            text="".join(texts),
            model=request.model,
            usage=usage,
            finish_reason=finish,
            tool_calls=calls,
        )

    async def test_connection(self, model: str) -> ConnectionResult:
        from google.genai import types

        started = time.perf_counter()
        try:
            self._require_key()
            response = await self._client.aio.models.generate_content(
                model=model,
                contents=[types.Content(role="user", parts=[types.Part(text="ping")])],
                config=types.GenerateContentConfig(max_output_tokens=5),
            )
            latency = int((time.perf_counter() - started) * 1000)
            reply = ""
            try:
                reply = (response.text or "").strip()[:40]
            except Exception:
                reply = ""
            detail = f"replied with {reply!r}" if reply else "replied"
            return ConnectionResult(True, model, latency, detail)
        except Exception as exc:
            latency = int((time.perf_counter() - started) * 1000)
            error = classify(exc)
            # Belt and braces: never surface key material in a diagnostic string.
            return ConnectionResult(
                False, model, latency, redact_text(error.friendly) or error.friendly
            )

    async def aclose(self) -> None:
        client = self._client
        try:
            await client.aio.aclose()
        except Exception:
            with contextlib.suppress(Exception):
                client.close()
