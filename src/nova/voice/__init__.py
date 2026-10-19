"""Voice I/O: microphone capture, speech-to-text and text-to-speech.

The heavy dependencies (``sounddevice``, ``faster-whisper``) are optional and
imported lazily, so this package imports cleanly without the ``voice`` extra and
reports availability through :func:`sound_available`.
"""

from nova.voice.devices import MicDevice, input_available, list_input_devices, sound_available
from nova.voice.service import VoiceService, VoiceState

__all__ = [
    "MicDevice",
    "VoiceService",
    "VoiceState",
    "input_available",
    "list_input_devices",
    "sound_available",
]
