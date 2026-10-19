"""Audio device discovery. Never raises when there is no microphone."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MicDevice:
    index: int
    name: str
    channels: int
    default: bool


def sound_available() -> bool:
    """Whether the optional audio stack (sounddevice + numpy) is importable."""
    try:
        import numpy  # noqa: F401
        import sounddevice  # noqa: F401
    except Exception:
        return False
    return True


def list_input_devices() -> list[MicDevice]:
    """Return the available input devices, or an empty list if none/absent."""
    try:
        import sounddevice as sd
    except Exception:
        return []

    try:
        devices = sd.query_devices()
        default_in = sd.default.device[0] if sd.default.device else -1
    except Exception:
        return []

    result: list[MicDevice] = []
    for index, device in enumerate(devices):
        channels = int(device.get("max_input_channels", 0) or 0)
        if channels > 0:
            result.append(
                MicDevice(
                    index=index,
                    name=str(device.get("name", f"device {index}")),
                    channels=channels,
                    default=index == default_in,
                )
            )
    return result


def input_available() -> bool:
    return bool(list_input_devices())
