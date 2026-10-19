"""The voice pipeline: listen -> transcribe -> answer -> speak.

Dependencies (capture, transcriber, speaker, chat) are injected so the whole
pipeline can be exercised with fakes — no microphone, no network, no model.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from nova.logging_setup import get_logger

Emit = Callable[[dict[str, Any]], Awaitable[None]]
ChatProvider = Callable[[], Any]

_LEVEL_INTERVAL = 0.06


class VoiceState(StrEnum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class VoiceService:
    """Coordinates capture, transcription, the chat pipeline and playback."""

    def __init__(
        self,
        *,
        chat: ChatProvider,
        capture_factory: Callable[[], Any],
        transcriber: Any,
        speaker: Any,
    ) -> None:
        self._chat = chat
        self._capture_factory = capture_factory
        self._transcriber = transcriber
        self._speaker = speaker
        self._log = get_logger("voice")
        self._capture: Any | None = None
        self._level_task: asyncio.Task | None = None
        self._state = VoiceState.IDLE
        self._emit: Emit | None = None
        self._conversation: str | None = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> VoiceState:
        return self._state

    @property
    def listening(self) -> bool:
        return self._capture is not None

    async def _emit_state(self, state: VoiceState, emit: Emit | None = None) -> None:
        self._state = state
        target = emit or self._emit
        if target is not None:
            await target({"type": "voice.state", "data": {"state": state.value}})

    async def start(self, emit: Emit) -> None:
        async with self._lock:
            if self._capture is not None:
                return
            self._emit = emit
            try:
                capture = self._capture_factory()
                capture.start()
            except Exception as exc:
                self._log.exception("could not start capture")
                await self._fail(emit, "microphone", str(exc))
                return
            self._capture = capture
            await self._emit_state(VoiceState.LISTENING, emit)
            self._level_task = asyncio.create_task(self._pump_levels(capture, emit))

    async def _pump_levels(self, capture: Any, emit: Emit) -> None:
        try:
            while True:
                await asyncio.sleep(_LEVEL_INTERVAL)
                await emit({"type": "voice.level", "data": {"level": round(capture.level(), 3)}})
        except asyncio.CancelledError:
            raise
        except Exception:
            self._log.debug("level pump stopped", exc_info=True)

    async def stop(self, emit: Emit) -> None:
        async with self._lock:
            capture = self._capture
            self._capture = None
            if capture is None:
                await self._emit_state(VoiceState.IDLE, emit)
                return
            await self._stop_levels()
            try:
                audio = capture.stop()
            except Exception:
                self._log.exception("capture stop failed")
                audio = None

        await self._emit_state(VoiceState.TRANSCRIBING, emit)
        try:
            text = (
                await self._transcriber.atranscribe(audio)
                if audio is not None and len(audio)
                else ""
            )
        except Exception as exc:
            self._log.warning("transcription failed: %s", exc)
            await self._fail(emit, "stt", "Could not transcribe that. Try again.")
            return

        await emit({"type": "voice.transcript", "data": {"text": text, "final": True}})
        if not text.strip():
            await self._emit_state(VoiceState.IDLE, emit)
            return

        await self._emit_state(VoiceState.THINKING, emit)
        spoken: list[str] = []

        async def relay(payload: dict[str, Any]) -> None:
            data = payload.get("data") or {}
            if payload.get("type") == "chat.delta":
                spoken.append(str(data.get("text", "")))
            if payload.get("type") == "chat.start" and data.get("conversation_id"):
                self._conversation = str(data["conversation_id"])
            await emit(payload)

        try:
            await self._chat().handle(text, conversation_id=self._conversation, emit=relay)
        except Exception:
            self._log.exception("voice chat failed")

        reply = "".join(spoken).strip()
        if reply:
            await self._emit_state(VoiceState.SPEAKING, emit)
            try:
                await self._speaker.aspeak(reply)
            except Exception:
                self._log.warning("speech playback failed", exc_info=True)
        await self._emit_state(VoiceState.IDLE, emit)

    async def cancel(self) -> None:
        async with self._lock:
            capture = self._capture
            self._capture = None
            await self._stop_levels()
            if capture is not None:
                try:
                    capture.stop()
                except Exception:
                    self._log.debug("capture stop during cancel failed", exc_info=True)
            await self._emit_state(VoiceState.IDLE)

    async def _stop_levels(self) -> None:
        task = self._level_task
        self._level_task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _fail(self, emit: Emit, kind: str, message: str) -> None:
        await emit({"type": "voice.error", "data": {"kind": kind, "message": message}})
        await self._emit_state(VoiceState.IDLE, emit)
