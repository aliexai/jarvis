"""Text-to-speech.

Two backends: a premium ElevenLabs voice when a key is configured, and an
offline Windows SAPI fallback that needs no key and no extra dependency.
"""

from __future__ import annotations

import asyncio
import io
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import httpx

from nova.errors import NovaError
from nova.logging_setup import get_logger

ELEVENLABS_ENDPOINT = "https://api.elevenlabs.io/v1/text-to-speech"
DEFAULT_MODEL = "eleven_flash_v2_5"
_PCM_RATE = 16_000

_SAPI_SCRIPT = (
    "Add-Type -AssemblyName System.Speech; "
    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
    "$s.Speak([Console]::In.ReadToEnd())"
)


class TextToSpeechError(NovaError):
    """Raised when speech synthesis is unavailable or fails."""


def _play_pcm(pcm_s16le: bytes, samplerate: int = _PCM_RATE) -> None:
    """Play raw 16-bit signed PCM by wrapping it in a WAV (Windows winsound)."""
    import winsound

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(samplerate)
        handle.writeframes(pcm_s16le)

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp.write(buffer.getvalue())
        path = tmp.name
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_NODEFAULT)
    finally:
        Path(path).unlink(missing_ok=True)


def _speak_sapi(text: str) -> None:
    """Speak with Windows SAPI. The text is passed on stdin, never interpolated."""
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", _SAPI_SCRIPT],
        input=text.strip(),
        text=True,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class Speaker:
    """Speak text through ElevenLabs when possible, otherwise Windows SAPI."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        voice_id: str | None = None,
        provider: str = "auto",
        model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key or ""
        self._voice_id = voice_id or ""
        self._provider = provider
        self._model = model
        self._timeout = timeout
        self._log = get_logger("voice.tts")

    @property
    def using_elevenlabs(self) -> bool:
        if self._provider == "sapi":
            return False
        return bool(self._api_key and self._voice_id)

    def _say_elevenlabs(self, text: str) -> None:
        response = httpx.post(
            f"{ELEVENLABS_ENDPOINT}/{self._voice_id}",
            params={"output_format": "pcm_16000"},
            headers={"xi-api-key": self._api_key, "Content-Type": "application/json"},
            json={"text": text, "model_id": self._model},
            timeout=self._timeout,
        )
        response.raise_for_status()
        _play_pcm(response.content)

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        if sys.platform != "win32":
            raise TextToSpeechError("no speech backend available on this platform")

        if self.using_elevenlabs:
            try:
                self._say_elevenlabs(text)
                return
            except Exception:
                self._log.warning(
                    "ElevenLabs playback failed; falling back to local speech", exc_info=True
                )
        _speak_sapi(text)

    async def aspeak(self, text: str) -> None:
        await asyncio.to_thread(self.speak, text)
