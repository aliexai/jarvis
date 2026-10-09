"""The frameless main window.

The window chrome is drawn by the web front-end (so it follows the active
theme). This class supplies what only the native layer can: minimise,
maximise/restore, close, a native drag via ``startSystemMove`` and native edge
resizing through ``WM_NCHITTEST``.

Window actions arrive from the API thread and are marshalled onto the Qt thread
by a queued signal connection.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QEvent, QObject, Qt, QUrl, Signal
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QMainWindow

from nova.api.server import CoreServer
from nova.api.state import CoreState
from nova.logging_setup import get_logger

# Windows messages / hit-test results.
WM_NCHITTEST = 0x0084
HTLEFT, HTRIGHT, HTTOP = 10, 11, 12
HTTOPLEFT, HTTOPRIGHT, HTBOTTOM = 13, 14, 15
HTBOTTOMLEFT, HTBOTTOMRIGHT = 16, 17

# Width of the invisible native resize border, in physical pixels.
_RESIZE_BORDER = 6


class WindowBridge(QObject):
    """Thread-safe relay from the API thread to the Qt thread."""

    actionRequested = Signal(str)


class MainWindow(QMainWindow):
    def __init__(
        self,
        state: CoreState,
        server: CoreServer,
        *,
        panel: str | None = None,
        theme: str | None = None,
        seed: str | None = None,
        scroll: int | None = None,
    ) -> None:
        super().__init__()
        self._state = state
        self._server = server
        self._log = get_logger("ui.window")

        self.setWindowTitle("NOVA")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1040, 660)
        self.resize(1400, 880)

        self._bridge = WindowBridge()
        self._bridge.actionRequested.connect(self._on_action, Qt.ConnectionType.QueuedConnection)
        state.window_action = self._bridge.actionRequested.emit

        self._view = QWebEngineView(self)
        self._view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setCentralWidget(self._view)
        self._view.load(QUrl(server.ui_url(panel=panel, theme=theme, seed=seed, scroll=scroll)))

    # -- actions from the web UI ------------------------------------------
    def _on_action(self, action: str) -> None:
        action = (action or "").strip().lower()
        self._log.info("window action: %s", action)
        if action == "minimize":
            self.showMinimized()
        elif action == "toggle-maximize":
            self.showNormal() if self.isMaximized() else self.showMaximized()
        elif action == "close":
            self.close()
        elif action == "start-move":
            handle = self.windowHandle()
            if handle is not None:
                handle.startSystemMove()

    # -- keep the web title bar in sync with the real window state ---------
    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            flag = "true" if self.isMaximized() else "false"
            page = self._view.page()
            if page is not None:
                page.runJavaScript(f"window.__novaWindowState && window.__novaWindowState({flag});")

    # -- native edge resizing for a frameless window ----------------------
    def nativeEvent(self, event_type, message):  # noqa: N802 (Qt override)
        if event_type == b"windows_generic_MSG":
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_NCHITTEST and not self.isMaximized():
                    code = self._hit_test()
                    if code is not None:
                        return True, code
            except Exception:  # pragma: no cover - defensive, never fatal
                pass
        return super().nativeEvent(event_type, message)

    def _hit_test(self) -> int | None:
        """Map the cursor position to a resize hit-test code."""
        try:
            user32 = ctypes.windll.user32
            hwnd = int(self.winId())
            rect = wintypes.RECT()
            if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return None
            point = wintypes.POINT()
            if not user32.GetCursorPos(ctypes.byref(point)):
                return None
        except Exception:  # pragma: no cover - non-Windows or blocked
            return None

        left = point.x - rect.left
        top = point.y - rect.top
        right = rect.right - point.x
        bottom = rect.bottom - point.y
        border = _RESIZE_BORDER

        on_left, on_right = left < border, right < border
        on_top, on_bottom = top < border, bottom < border

        if on_top and on_left:
            return HTTOPLEFT
        if on_top and on_right:
            return HTTOPRIGHT
        if on_bottom and on_left:
            return HTBOTTOMLEFT
        if on_bottom and on_right:
            return HTBOTTOMRIGHT
        if on_left:
            return HTLEFT
        if on_right:
            return HTRIGHT
        if on_top:
            return HTTOP
        if on_bottom:
            return HTBOTTOM
        return None
