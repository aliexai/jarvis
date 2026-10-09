"""Command-line entry point.

Currently exposes a small diagnostics command used to verify an install. The
GUI is launched from a later phase.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys

from nova import __version__
from nova.config import get_paths, load_settings
from nova.logging_setup import get_logger
from nova.security.secrets import KNOWN_SECRETS, SecretStore, ignored_legacy_env


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nova", description="NOVA command-center assistant")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("version", help="print the version and exit")
    sub.add_parser("diag", help="print environment and configuration diagnostics")
    return parser


def _diagnostics(store: SecretStore | None = None) -> dict:
    """Build the diagnostics report. Never includes key material."""
    paths = get_paths()
    settings = load_settings(paths=paths)
    store = store or SecretStore()

    warnings: list[str] = []
    secrets: dict[str, dict] = {}
    for name in KNOWN_SECRETS:
        resolved = store.resolve(name)
        ok, warning = resolved.prefix_check()
        secrets[name] = {
            "source": resolved.source,
            "value": resolved.masked,
            "prefix_ok": ok,
        }
        if warning:
            warnings.append(warning)

    ignored = ignored_legacy_env()
    if ignored:
        warnings.append(
            "ignoring unprefixed environment variables (not read by NOVA): " + ", ".join(ignored)
        )

    return {
        "nova_version": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "paths": {
            "root": str(paths.root),
            "config": str(paths.config),
            "logs": str(paths.logs),
            "settings_file": str(paths.settings_file),
            "settings_exists": paths.settings_file.exists(),
        },
        "settings": {
            "version": settings.version,
            "log_level": settings.log_level,
            "theme": settings.ui.theme,
            "performance_mode": settings.ui.performance_mode,
            "models": {"fast": settings.models.fast, "strong": settings.models.strong},
            "voice": {
                "tts_provider": settings.voice.tts_provider,
                "stt_engine": settings.voice.stt_engine,
                "language": settings.voice.language,
            },
            "security": {
                "allowed_folders": len(settings.security.allowed_folders),
                "allowed_apps": len(settings.security.allowed_apps),
                "allowed_domains": len(settings.security.allowed_domains),
                "allowed_commands": len(settings.security.allowed_commands),
            },
        },
        "secrets": {
            "keyring_available": store.keyring_available,
            **secrets,
        },
        "warnings": warnings,
    }


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "version":
        print(__version__)
        return 0

    if args.command == "diag":
        report = _diagnostics()
        print(json.dumps(report, indent=2, ensure_ascii=False))
        for warning in report["warnings"]:
            get_logger("cli").warning(warning)
        get_logger("cli").info("diagnostics exported")
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
