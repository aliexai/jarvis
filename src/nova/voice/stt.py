"""Local speech-to-text with faster-whisper.

The model is loaded lazily on first use, so constructing a :class:`Transcriber`
is cheap and safe even when the ``voice`` extra is absent.
"""

from __future__ import annotations

import asyncio
from typing import Any

from nova.errors import NovaError
from nova.logging_setup import get_logger


class SpeechToTextError(NovaError):
    """Raised when transcription is unavailable or fails."""


class Transcriber:
    def __init__(self, *, model_size: str = "base", language: str = "en") -> None:
        self._model_size = model_size
        self._language = language
        self._model: Any | None = None
        self._log = get_logger("voice.stt")

    def _load(self) -> Any:
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
            except Exception as exc:
                raise SpeechToTextError("speech-to-text engine is not installed") from exc
            self._log.info("loading whisper model %s", self._model_size)
            self._model = WhisperModel(self._model_size, device="cpu", compute_type="int8")
        return self._model

    def transcribe(self, audio: Any) -> str:
        model = self._load()
        try:
            segments, _info = model.transcribe(audio, language=self._language, beam_size=1)
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            raise SpeechToTextError(f"transcription failed: {exc}") from exc

    async def atranscribe(self, audio: Any) -> str:
        return await asyncio.to_thread(self.transcribe, audio)
