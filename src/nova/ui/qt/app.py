"""Application runner: single-instance, DPI policy, server, window and tray.

Also hosts the verification harness used to prove the app runs:

* ``--shot <path>``     capture the window to a PNG and exit
* ``--measure <secs>``  measure idle resident memory of the process tree and exit

Both wait for the web UI to report ready before acting.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from pathlib import Path

# QtWebEngine must be imported before QApplication is constructed.
from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QImage, QPixmap
from PySide6.QtWebEngineWidgets import QWebEngineView  # noqa: F401
from PySide6.QtWidgets import QApplication

from nova import __version__
from nova.api.server import CoreServer
from nova.api.state import CoreState
from nova.config import get_paths, load_settings
from nova.logging_setup import get_logger, setup_logging
from nova.ui.qt.tray import create_tray, make_icon
from nova.ui.qt.window import MainWindow

_READY_POLL_MS = 200
_SETTLE_MS = 1200


def dist_dir() -> Path:
    """Locate the built front-end bundle."""
    override = os.environ.get("NOVA_UI_DIST")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "ui" / "web" / "dist"


# -- harness helpers -------------------------------------------------------
def _is_blank(pixmap: QPixmap) -> bool:
    image = pixmap.toImage()
    if image.isNull() or image.width() < 4 or image.height() < 4:
        return True
    colours: set[int] = set()
    step_x = max(1, image.width() // 24)
    step_y = max(1, image.height() // 24)
    for x in range(0, image.width(), step_x):
        for y in range(0, image.height(), step_y):
            colours.add(image.pixel(x, y))
            if len(colours) > 4:
                return False
    return len(colours) <= 1


def _grab_with_mss(window) -> QPixmap | None:
    try:
        import ctypes
        from ctypes import wintypes

        import mss

        rect = wintypes.RECT()
        if not ctypes.windll.user32.GetWindowRect(int(window.winId()), ctypes.byref(rect)):
            return None
        box = {
            "left": rect.left,
            "top": rect.top,
            "width": rect.right - rect.left,
            "height": rect.bottom - rect.top,
        }
        with mss.mss() as capturer:
            raw = capturer.grab(box)
        image = QImage(bytes(raw.rgb), raw.width, raw.height, QImage.Format.Format_RGB888)
        return QPixmap.fromImage(image)
    except Exception:
        return None


def capture_window(window, out_path: Path) -> bool:
    """Capture the window to ``out_path``. Tries Qt first, then mss."""
    window.raise_()
    window.activateWindow()
    QApplication.processEvents()
    time.sleep(0.35)
    QApplication.processEvents()

    pixmap: QPixmap | None = None
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        grabbed = screen.grabWindow(int(window.winId()))
        if not grabbed.isNull() and not _is_blank(grabbed):
            pixmap = grabbed
    if pixmap is None:
        pixmap = _grab_with_mss(window)
    if pixmap is None:
        return False

    out_path.parent.mkdir(parents=True, exist_ok=True)
    return bool(pixmap.save(str(out_path), "PNG"))


def tree_memory() -> dict:
    """Resident memory of this process and all of its children, with a breakdown."""
    import psutil

    process = psutil.Process()
    entries: list[dict] = []
    total = 0
    members = [process, *process.children(recursive=True)]
    for member in members:
        try:
            rss = member.memory_info().rss
            name = member.name()
        except Exception:
            continue
        total += rss
        entries.append({"pid": member.pid, "name": name, "rss_mb": round(rss / (1024 * 1024), 1)})
    return {
        "resident_mb": round(total / (1024 * 1024), 1),
        "processes": len(entries),
        "breakdown": entries,
    }


def _when_ready(
    window, state: CoreState, callback, settle_ms: int = _SETTLE_MS, timeout_ms: int = 40_000
) -> QTimer:
    """Poll until the UI reports ready, settle briefly, then call ``callback``."""
    timer = QTimer(window)
    elapsed = {"ms": 0}

    def tick() -> None:
        elapsed["ms"] += _READY_POLL_MS
        if state.ui_ready.is_set() or elapsed["ms"] >= timeout_ms:
            timer.stop()
            QTimer.singleShot(settle_ms, callback)

    timer.timeout.connect(tick)
    timer.start(_READY_POLL_MS)
    return timer


# -- entry point -----------------------------------------------------------
def run(
    *,
    panel: str | None = None,
    theme: str | None = None,
    seed: str | None = None,
    scroll: int | None = None,
    shot: str | None = None,
    shot_delay: float = _SETTLE_MS / 1000,
    measure: float | None = None,
    out: str | None = None,
) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(sys.argv[:1])
    app.setApplicationName("NOVA")
    app.setOrganizationName("Nova")
    app.setApplicationVersion(__version__)
    app.setQuitOnLastWindowClosed(False)

    paths = get_paths().ensure()
    settings = load_settings(paths=paths)
    setup_logging(paths, level=settings.log_level)
    log = get_logger("ui")
    log.info("starting NOVA %s on Python %s", __version__, sys.version.split()[0])

    lock = QLockFile(str(paths.cache / "nova-ui.lock"))
    lock.setStaleLockTime(30_000)
    if not lock.tryLock(200):
        log.warning("another NOVA instance is already running")
        print("NOVA is already running.", file=sys.stderr)
        return 1

    state = CoreState.create(token=secrets.token_urlsafe(32), paths=paths, settings=settings)
    server = CoreServer(state, static_dir=dist_dir())
    try:
        server.start()
    except Exception:
        log.exception("failed to start the core server")
        print("Failed to start the local API.", file=sys.stderr)
        return 1

    def quit_app() -> None:
        server.stop()
        state.close()
        app.quit()

    window = MainWindow(state, server, panel=panel, theme=theme, seed=seed, scroll=scroll)
    icon = make_icon()
    window.setWindowIcon(icon)
    window.show()
    tray = create_tray(app, window, on_quit=quit_app)
    app.aboutToQuit.connect(lambda: tray.hide())

    if shot:

        def take_shot() -> None:
            target = Path(shot)
            ok = capture_window(window, target)
            print(
                json.dumps(
                    {
                        "screenshot": str(target),
                        "ok": ok,
                        "panel": panel,
                        "theme": theme or settings.ui.theme,
                    }
                )
            )
            quit_app()

        _when_ready(window, state, take_shot, settle_ms=int(max(0.0, shot_delay) * 1000))

    if measure is not None:

        def do_measure() -> None:
            reading = tree_memory()
            reading["waiting_seconds"] = measure
            print(json.dumps(reading))
            if out:
                Path(out).write_text(json.dumps(reading, indent=2), encoding="utf-8")
            quit_app()

        QTimer.singleShot(int(max(0.0, measure) * 1000), do_measure)

    log.info(
        "UI available at %s",
        server.ui_url(panel=panel, theme=theme, seed=seed, scroll=scroll),
    )
    code = app.exec()
    server.stop()
    state.close()
    return code
