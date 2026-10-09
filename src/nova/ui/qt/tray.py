"""System tray icon and menu.

The icon is drawn procedurally (a glowing orb) so no image asset is required,
and it is re-tinted to match the active theme.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

ACCENTS: dict[str, str] = {
    "cyan": "#22d3ee",
    "emerald": "#34d399",
    "crimson": "#f43f5e",
}


def make_icon(accent: str = "#22d3ee", size: int = 64) -> QIcon:
    """Draw the NOVA orb icon in the given accent colour."""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    colour = QColor(accent)

    glow = QRadialGradient(size / 2, size / 2, size / 2)
    glow.setColorAt(0.0, QColor(colour.red(), colour.green(), colour.blue(), 235))
    glow.setColorAt(0.55, QColor(colour.red(), colour.green(), colour.blue(), 90))
    glow.setColorAt(1.0, QColor(colour.red(), colour.green(), colour.blue(), 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(glow)
    painter.drawEllipse(1, 1, size - 2, size - 2)

    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.setPen(QPen(colour, max(1, size // 22)))
    inset = size * 0.24
    painter.drawEllipse(int(inset), int(inset), int(size - inset * 2), int(size - inset * 2))
    painter.end()

    return QIcon(pixmap)


def _show(window) -> None:
    window.show()
    window.raise_()
    window.activateWindow()


def create_tray(
    app: QApplication,
    window,
    on_quit: Callable[[], None],
    accent: str = "#22d3ee",
) -> QSystemTrayIcon:
    """Create and show the tray icon with its quick actions."""
    tray = QSystemTrayIcon(make_icon(accent), app)
    tray.setToolTip("NOVA - Command Center")

    menu = QMenu()
    open_action = QAction("Open NOVA", menu)
    open_action.triggered.connect(lambda: _show(window))
    hide_action = QAction("Hide to tray", menu)
    hide_action.triggered.connect(window.hide)
    quit_action = QAction("Quit", menu)
    quit_action.triggered.connect(on_quit)

    menu.addAction(open_action)
    menu.addAction(hide_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray.setContextMenu(menu)

    tray.activated.connect(
        lambda reason: (
            _show(window) if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
    )
    tray.show()
    return tray
