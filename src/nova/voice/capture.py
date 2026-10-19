"""Push-to-talk microphone capture with a live RMS level.

Heavy imports (``numpy``, ``sounddevice``) happen inside the methods so the
module can be imported without the optional audio stack.
"""

from __future__ import annotations

import threading
from typing import Any

from nova.logging_setup import get_logger

SAMPLE_RATE = 16_000


class MicCapture:
    """Capture mono float32 audio from an input device.

    ``level`` returns the newest RMS amplitude and is safe to poll from another
    thread; :meth:`stop` returns everything recorded as a numpy array.
    """

    def __init__(self, *, device: int | None = None, samplerate: int = SAMPLE_RATE) -> None:
        self._device = device
        self._samplerate = samplerate
        self._log = get_logger("voice.capture")
        self._stream: Any | None = None
        self._frames: list[Any] = []
        self._level = 0.0
        self._lock = threading.Lock()
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def level(self) -> float:
        return self._level

    def start(self) -> None:
        import numpy as np
        import sounddevice as sd

        block = int(self._samplerate * 0.05)  # 50 ms frames

        def callback(indata: Any, frames: int, time_info: Any, status: Any) -> None:
            if status:
                self._log.debug("capture status: %s", status)
            samples = np.asarray(indata[:, 0], dtype="float32")
            rms = float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0
            with self._lock:
                self._frames.append(samples.copy())
                self._level = min(1.0, rms * 6.0)

        self._frames = []
        self._level = 0.0
        self._stream = sd.InputStream(
            samplerate=self._samplerate,
            channels=1,
            dtype="float32",
            blocksize=block,
            device=self._device,
            callback=callback,
        )
        self._stream.start()
        self._active = True

    def stop(self) -> Any:
        import numpy as np

        stream = self._stream
        self._stream = None
        self._active = False
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                self._log.debug("closing the capture stream failed", exc_info=True)

        with self._lock:
            frames = self._frames
            self._frames = []
            self._level = 0.0
        if not frames:
            return np.zeros(0, dtype="float32")
        return np.concatenate(frames)
