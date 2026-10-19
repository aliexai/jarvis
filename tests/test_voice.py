"""Tests for the voice pipeline, devices and the API surface.

The pipeline is exercised with fake capture/transcriber/speaker, so these run
without a microphone, a model download or any network.
"""

from __future__ import annotations

import asyncio

import pytest

from nova.voice.devices import input_available, list_input_devices, sound_available
from nova.voice.service import VoiceService


class FakeCapture:
    def __init__(self, audio: list[float] | None = None, level: float = 0.4) -> None:
        self.audio = audio if audio is not None else [0.0] * 1600
        self._level = level
        self.started = False
        self.stopped = False

    def start(self) -> None:
        self.started = True

    def level(self) -> float:
        return self._level

    def stop(self) -> list[float]:
        self.stopped = True
        return self.audio


class FailingCapture:
    def start(self) -> None:
        raise RuntimeError("no microphone")

    def level(self) -> float:
        return 0.0

    def stop(self) -> list[float]:
        return []


class FakeTranscriber:
    def __init__(self, text: str = "hello nova", *, fail: bool = False) -> None:
        self.text = text
        self.fail = fail

    async def atranscribe(self, audio: object) -> str:
        if self.fail:
            raise RuntimeError("stt down")
        return self.text


class FakeSpeaker:
    def __init__(self) -> None:
        self.spoken: list[str] = []

    async def aspeak(self, text: str) -> None:
        self.spoken.append(text)


class FakeChat:
    def __init__(self, reply: str = "Hi there.") -> None:
        self.reply = reply
        self.calls: list[str] = []

    async def handle(self, text, *, conversation_id, emit, model_override=None):  # noqa: ANN001
        self.calls.append(text)
        await emit(
            {
                "type": "chat.start",
                "data": {"id": "m1", "conversation_id": "c1", "model": "mock", "tier": "fast"},
            }
        )
        for piece in self.reply.split():
            await emit({"type": "chat.delta", "data": {"id": "m1", "text": piece + " "}})
        await emit({"type": "chat.done", "data": {"id": "m1"}})


async def _run(service: VoiceService) -> list[dict]:
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    await service.start(emit)
    await asyncio.sleep(0.15)  # let the level pump emit at least once
    await service.stop(emit)
    return events


def _states(events: list[dict]) -> list[str]:
    return [e["data"]["state"] for e in events if e["type"] == "voice.state"]


async def test_full_cycle_listens_transcribes_answers_and_speaks():
    chat = FakeChat(reply="Hi there.")
    speaker = FakeSpeaker()
    capture = FakeCapture()
    service = VoiceService(
        chat=lambda: chat,
        capture_factory=lambda: capture,
        transcriber=FakeTranscriber("what is up"),
        speaker=speaker,
    )

    events = await _run(service)

    assert capture.started is True
    assert capture.stopped is True
    assert chat.calls == ["what is up"]
    assert speaker.spoken == ["Hi there."]
    assert any(e["type"] == "voice.level" for e in events)
    transcript = [e for e in events if e["type"] == "voice.transcript"]
    assert transcript and transcript[0]["data"]["text"] == "what is up"
    states = _states(events)
    assert "listening" in states
    assert "thinking" in states
    assert "speaking" in states
    assert states[-1] == "idle"


async def test_silence_goes_straight_back_to_idle():
    chat = FakeChat()
    speaker = FakeSpeaker()
    service = VoiceService(
        chat=lambda: chat,
        capture_factory=lambda: FakeCapture(),
        transcriber=FakeTranscriber("   "),
        speaker=speaker,
    )

    events = await _run(service)

    assert chat.calls == []
    assert speaker.spoken == []
    assert _states(events)[-1] == "idle"


async def test_microphone_failure_reports_error():
    service = VoiceService(
        chat=lambda: FakeChat(),
        capture_factory=lambda: FailingCapture(),
        transcriber=FakeTranscriber(),
        speaker=FakeSpeaker(),
    )
    events: list[dict] = []

    async def emit(payload: dict) -> None:
        events.append(payload)

    await service.start(emit)

    errors = [e for e in events if e["type"] == "voice.error"]
    assert errors and errors[0]["data"]["kind"] == "microphone"


async def test_transcription_failure_reports_error():
    service = VoiceService(
        chat=lambda: FakeChat(),
        capture_factory=lambda: FakeCapture(),
        transcriber=FakeTranscriber(fail=True),
        speaker=FakeSpeaker(),
    )

    events = await _run(service)

    errors = [e for e in events if e["type"] == "voice.error"]
    assert errors and errors[0]["data"]["kind"] == "stt"


async def test_cancel_stops_capture():
    capture = FakeCapture()
    service = VoiceService(
        chat=lambda: FakeChat(),
        capture_factory=lambda: capture,
        transcriber=FakeTranscriber(),
        speaker=FakeSpeaker(),
    )

    async def emit(payload: dict) -> None:
        return None

    await service.start(emit)
    assert service.listening is True
    await service.cancel()
    assert service.listening is False
    assert capture.stopped is True


def test_device_discovery_never_raises():
    devices = list_input_devices()
    assert isinstance(devices, list)
    assert isinstance(sound_available(), bool)
    assert isinstance(input_available(), bool)


@pytest.mark.parametrize("provider", ["auto", "elevenlabs", "sapi"])
def test_speaker_reports_backend(provider: str):
    from nova.voice.tts import Speaker

    speaker = Speaker(provider=provider)
    assert isinstance(speaker.using_elevenlabs, bool)
