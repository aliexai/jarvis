"""Structured (JSON-mode) output with schema validation and a retry."""

from __future__ import annotations

import json
from typing import Any

from nova.providers.base import LLMProvider, LLMRequest, Message
from nova.providers.errors import JsonSchemaError
from nova.validation import validate


def extract_json(text: str) -> Any | None:
    """Parse JSON, tolerating a surrounding markdown code fence."""
    candidate = (text or "").strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None


async def generate_json(
    provider: LLMProvider,
    *,
    model: str,
    prompt: str,
    schema: dict[str, Any],
    system_instruction: str | None = None,
    retries: int = 1,
    temperature: float = 0.0,
    max_output_tokens: int | None = None,
) -> Any:
    """Ask for JSON matching ``schema``, retrying once (by default) on mismatch.

    Raises :class:`JsonSchemaError` if the model cannot produce valid output.
    """
    messages: list[Message] = [Message("user", prompt)]
    last_error = "no attempt made"

    for attempt in range(retries + 1):
        request = LLMRequest(
            model=model,
            messages=list(messages),
            system_instruction=system_instruction,
            json_schema=schema,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )
        completion = await provider.complete(request)
        text = completion.text

        parsed = extract_json(text)
        if parsed is not None:
            errors = validate(parsed, schema)
            if not errors:
                return parsed
            last_error = "; ".join(errors[:5])
        else:
            last_error = "the response was not valid JSON"

        if attempt < retries:
            messages.append(Message("model", text or "(empty response)"))
            messages.append(
                Message(
                    "user",
                    "That reply did not satisfy the schema: "
                    f"{last_error}. Reply with only JSON that matches the schema.",
                )
            )

    raise JsonSchemaError(f"structured output invalid after {retries + 1} attempts: {last_error}")
