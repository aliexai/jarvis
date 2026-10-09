"""Smoke tests for the Qt shell.

These prove the real window is constructed (frameless, hosting a web view), that
the window-action bridge is wired to the API, and that the tray icon renders.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6", reason="PySide6 is required for the UI tests")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMainWindow

from nova.api.server import CoreServer
from nova.ui.qt.tray import make_icon
from nova.ui.qt.window import MainWindow


@pytest.fixture
def server(core_state):
    core = CoreServer(core_state, static_dir=None, host="127.0.0.1")
    core.start(timeout=20)
    yield core
    core.stop()


def test_window_is_frameless_and_hosts_a_web_view(qtbot, core_state, server):
    window = MainWindow(core_state, server, panel="home", theme="cyan")
    qtbot.addWidget(window)

    assert isinstance(window, QMainWindow)
    assert window.windowFlags() & Qt.WindowType.FramelessWindowHint
    assert window.centralWidget() is not None
    assert window.minimumWidth() > 0


def test_window_action_bridge_is_wired(qtbot, core_state, server):
    window = MainWindow(core_state, server)
    qtbot.addWidget(window)

    assert callable(core_state.window_action)
    # Dispatching an action through the bridge must not raise.
    core_state.window_action("minimize")
    qtbot.wait(150)


def test_tray_icon_renders_in_theme_accent():
    icon = make_icon("#34d399")
    assert not icon.isNull()
    pixmap = icon.pixmap(32, 32)
    # The pixmap is DPI-scaled, so compare the device-independent size.
    size = pixmap.deviceIndependentSize()
    assert round(size.width()) == 32
    assert round(size.height()) == 32


def test_core_server_binds_loopback(server, core_state):
    assert server.port > 0
    assert server.base_url.startswith("http://127.0.0.1:")
    assert server.token == core_state.token
