"""Mock chat backend for Phase 2.

Produces realistic, markdown-formatted streaming text so the Chat panel,
markdown rendering and code blocks can be exercised before the real Gemini
provider lands in Phase 3. No network access.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

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

Want me to add a `pytest` case for the empty-input path?"""

_GENERAL_REPLY = """Good question. Here's how I'd approach **"{prompt}"**:

1. Restate the goal and the constraints so we agree on the target.
2. Break it into small, independently verifiable steps.
3. Do the smallest useful slice first, then iterate.

The important part is that each step produces something you can actually check,
rather than a large change you have to trust. Tell me which step you want to
start with and I'll dig in.

> Note: I'm running on the **mock backend** in Phase 2, so this reply is canned.
> The real model arrives in Phase 3."""

_SUMMARY_REPLY = """Here's a summary:

- **Status:** all checks passing.
- **Changed:** `nova/api/`, `nova/ui/` and the front-end shell.
- **Next:** wire the real Gemini provider.

```bash
python -m pytest
nova ui
```"""


def reply_for(text: str) -> str:
    """Pick a canned reply based on simple keywords."""
    lowered = text.lower()
    if any(word in lowered for word in ("code", "python", "function", "script", "test")):
        return _CODE_REPLY
    if any(word in lowered for word in ("summary", "summarise", "summarize", "status", "report")):
        return _SUMMARY_REPLY
    return _GENERAL_REPLY.format(prompt=text.strip()[:80])


def _chunks(text: str, words_per_chunk: int = 3) -> list[str]:
    words = text.split(" ")
    chunks: list[str] = []
    for index in range(0, len(words), words_per_chunk):
        group = words[index : index + words_per_chunk]
        is_last = index + words_per_chunk >= len(words)
        chunks.append(" ".join(group) if is_last else " ".join(group) + " ")
    return chunks


async def stream_reply(text: str, *, delay: float = 0.018) -> AsyncIterator[str]:
    """Yield the reply in small chunks with a short delay between them."""
    for chunk in _chunks(reply_for(text)):
        yield chunk
        await asyncio.sleep(delay)
