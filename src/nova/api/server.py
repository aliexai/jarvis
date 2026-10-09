"""Supervised local HTTP/WebSocket server.

uvicorn runs in its own thread with its own event loop. It only installs signal
handlers in the main thread, so running it here keeps the Qt event loop in
charge of the process. The socket is always bound to loopback.
"""

from __future__ import annotations

import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import uvicorn

from nova.api.app import create_app
from nova.api.state import CoreState
from nova.logging_setup import get_logger


def free_port(host: str = "127.0.0.1") -> int:
    """Ask the OS for an unused TCP port on ``host``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class CoreServer:
    """Runs the local API for one session."""

    def __init__(
        self,
        state: CoreState,
        static_dir: Path | None = None,
        host: str = "127.0.0.1",
    ) -> None:
        self._state = state
        self._static_dir = static_dir
        self._host = host
        self._port: int | None = None
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None

    def start(self, timeout: float = 20.0) -> CoreServer:
        self._port = free_port(self._host)
        app = create_app(self._state, self._static_dir)
        config = uvicorn.Config(
            app,
            host=self._host,
            port=self._port,
            log_level="warning",
            access_log=False,
            lifespan="on",
        )
        self._server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self._server.run, name="nova-core", daemon=True)
        self._thread.start()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started:
                get_logger("core").info("core server listening on %s", self.base_url)
                return self
            if not self._thread.is_alive():
                raise RuntimeError("core server thread exited during startup")
            time.sleep(0.05)
        raise RuntimeError("core server did not become ready in time")

    def stop(self, timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)

    @property
    def port(self) -> int:
        if self._port is None:
            raise RuntimeError("server has not been started")
        return self._port

    @property
    def token(self) -> str:
        return self._state.token

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self.port}"

    def ui_url(
        self,
        *,
        panel: str | None = None,
        theme: str | None = None,
        seed: str | None = None,
        scroll: int | None = None,
    ) -> str:
        params: dict[str, str] = {"token": self.token}
        if panel:
            params["panel"] = panel
        if theme:
            params["theme"] = theme
        if seed:
            params["seed"] = seed
        if scroll:
            params["scroll"] = str(scroll)
        return f"{self.base_url}/?{urlencode(params)}"
