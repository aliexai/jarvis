"""Command-line entry point.

Commands:

* ``nova version``  - print the version
* ``nova diag``     - print environment/configuration diagnostics (never keys)
* ``nova ui``       - launch the desktop Command Center
"""

from __future__ import annotations

import argparse
import json
import sys

from nova.diagnostics import build_diagnostics

PANELS = (
    "home",
    "chat",
    "agent-town",
    "tasks",
    "coding",
    "memory",
    "world-monitor",
    "system",
    "settings",
)
THEMES = ("cyan", "emerald", "crimson")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova", description="NOVA command-center assistant")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("version", help="print the version and exit")
    sub.add_parser("diag", help="print environment and configuration diagnostics")

    ui = sub.add_parser("ui", help="launch the desktop Command Center")
    ui.add_argument("--panel", choices=PANELS, default=None, help="open a specific panel")
    ui.add_argument("--theme", choices=THEMES, default=None, help="force a theme for this run")
    ui.add_argument(
        "--seed",
        default=None,
        help="send this chat message once connected (demo/screenshot helper)",
    )
    ui.add_argument(
        "--scroll",
        type=int,
        default=None,
        help="scroll the opened panel to this offset (demo/screenshot helper)",
    )
    ui.add_argument(
        "--shot",
        metavar="PATH",
        default=None,
        help="capture the window to PATH once loaded, then exit",
    )
    ui.add_argument(
        "--shot-delay",
        type=float,
        default=1.2,
        metavar="SECONDS",
        help="settle time after the UI is ready before capturing (default 1.2)",
    )
    ui.add_argument(
        "--measure",
        type=float,
        metavar="SECONDS",
        default=None,
        help="measure idle memory after SECONDS, print it, then exit",
    )
    ui.add_argument("--out", default=None, help="write the measurement JSON to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        from nova import __version__

        print(__version__)
        return 0

    if args.command == "diag":
        print(json.dumps(build_diagnostics(), indent=2, ensure_ascii=False))
        return 0

    if args.command == "ui":
        try:
            from nova.ui.qt.app import run as run_ui
        except ImportError:
            print(
                "PySide6 is required for the UI. Install it with:\n"
                '  python -m pip install -e ".[ui]"',
                file=sys.stderr,
            )
            return 2
        return run_ui(
            panel=args.panel,
            theme=args.theme,
            seed=args.seed,
            scroll=args.scroll,
            shot=args.shot,
            shot_delay=args.shot_delay,
            measure=args.measure,
            out=args.out,
        )

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
