"""Model routing tests."""

from __future__ import annotations

from nova.providers.routing import choose_model

FAST = "fast-model"
STRONG = "strong-model"


def route(text: str, mode: str = "auto"):
    return choose_model(text, fast_model=FAST, strong_model=STRONG, mode=mode)  # type: ignore[arg-type]


def test_short_simple_request_uses_the_fast_model():
    decision = route("what is a variable")
    assert decision.tier == "fast"
    assert decision.model == FAST


def test_long_input_uses_the_strong_model():
    decision = route("explain this " + "word " * 100)
    assert decision.tier == "strong"
    assert decision.reason == "long input"


def test_coding_request_uses_the_strong_model():
    assert route("why does this code fail: ```def f():```").tier == "strong"
    assert route("please refactor this function").tier == "strong"
    assert route("here is a traceback").tier == "strong"


def test_planning_request_uses_the_strong_model():
    assert route("plan the architecture for this feature").tier == "strong"
    assert route("explain how the cache works").tier == "strong"


def test_multi_part_question_uses_the_strong_model():
    assert route("what is a? what is b? what is c?").tier == "strong"


def test_manual_override_fast():
    decision = route("refactor this code", mode="fast")
    assert decision.tier == "fast"
    assert decision.model == FAST
    assert decision.forced is True


def test_manual_override_strong():
    decision = route("hi", mode="strong")
    assert decision.tier == "strong"
    assert decision.model == STRONG
    assert decision.forced is True


def test_auto_routing_is_not_marked_forced():
    assert route("what is a variable").forced is False
