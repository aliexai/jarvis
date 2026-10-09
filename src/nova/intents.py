"""Local intents answered without calling the AI.

Keeps trivial, deterministic questions ("what time is it?") free and instant.
Deliberately conservative: a pattern only matches a short, clearly local
request, so real questions are never hijacked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

MAX_LOCAL_INTENT_CHARS = 48


@dataclass(frozen=True)
class LocalIntent:
    name: str
    reply: str


_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "time",
        re.compile(
            r"^(what(?:'s| is)? the time|what time is it|what'?s the time"
            r"|current time|time now|the time)$"
        ),
    ),
    (
        "date",
        re.compile(
            r"^(what(?:'s| is)? the date|what day is it|today'?s date"
            r"|what'?s today'?s date|the date)$"
        ),
    ),
    (
        "identity",
        re.compile(r"^(who are you|what are you|what'?s your name|your name)$"),
    ),
    ("greeting", re.compile(r"^(hi|hey|hello|good (?:morning|afternoon|evening))$")),
    ("thanks", re.compile(r"^(thanks|thank you|ta)$")),
)


def _normalise(text: str) -> str:
    """Lowercase and drop trailing punctuation, so "time?" == "time"."""
    return re.sub(r"[\s?!.,]+$", "", text.strip().lower())


def _now() -> datetime:
    return datetime.now().astimezone()


def match_local_intent(text: str) -> LocalIntent | None:
    """Return a locally-answerable intent, or ``None`` to use the model.

    Matching is deliberately whole-message: "what is the time complexity of
    quicksort" must reach the model, not the clock.
    """
    candidate = (text or "").strip()
    if not candidate or len(candidate) > MAX_LOCAL_INTENT_CHARS:
        return None

    lowered = _normalise(candidate)
    for name, pattern in _PATTERNS:
        if pattern.fullmatch(lowered) is None:
            continue
        if name == "time":
            return LocalIntent("time", f"It's {_now().strftime('%H:%M')} local time.")
        if name == "date":
            return LocalIntent("date", f"Today is {_now().strftime('%A, %d %B %Y')}.")
        if name == "identity":
            return LocalIntent(
                "identity",
                "I'm NOVA, your local command-center assistant. I run on this machine "
                "and only call the AI when a request actually needs it.",
            )
        if name == "greeting":
            return LocalIntent("greeting", "Hello. What would you like to do?")
        if name == "thanks":
            return LocalIntent("thanks", "Any time.")
    return None
