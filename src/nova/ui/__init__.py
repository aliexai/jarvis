"""PySide6 desktop shell."""

from __future__ import annotations

__all__ = ["run"]


def run(**kwargs) -> int:  # pragma: no cover - thin re-export
    from nova.ui.qt.app import run as _run

    return _run(**kwargs)
