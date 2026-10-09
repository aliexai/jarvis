"""Local intent tests."""

from __future__ import annotations

from nova.intents import match_local_intent


def test_time_intent():
    intent = match_local_intent("what time is it?")
    assert intent is not None
    assert intent.name == "time"
    assert ":" in intent.reply


def test_alternate_time_phrasings():
    for text in ("what's the time", "current time", "time now"):
        intent = match_local_intent(text)
        assert intent is not None and intent.name == "time"


def test_date_intent():
    intent = match_local_intent("what's the date?")
    assert intent is not None
    assert intent.name == "date"


def test_greeting_intent():
    intent = match_local_intent("hello")
    assert intent is not None
    assert intent.name == "greeting"


def test_identity_intent():
    intent = match_local_intent("who are you?")
    assert intent is not None
    assert intent.name == "identity"


def test_thanks_intent():
    intent = match_local_intent("thanks")
    assert intent is not None
    assert intent.name == "thanks"


def test_substantive_questions_are_not_hijacked():
    for text in (
        "what is the time complexity of quicksort",
        "explain how the garbage collector works",
        "write me a python function",
        "summarise this document for me please now",
        "hello, can you explain how transformers work in detail",
    ):
        assert match_local_intent(text) is None


def test_empty_and_long_input_are_ignored():
    assert match_local_intent("") is None
    assert match_local_intent("   ") is None
    assert match_local_intent("what time is it? " + "x" * 60) is None
