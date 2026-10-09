"""Diagnostics report shared by the CLI and the local API.

The report never contains key material: secrets are reported by source and
masked length only, plus a public-prefix sanity check.
"""

from __future__ import annotations

import platform
import sys

from nova import __version__
from nova.config import get_paths, load_settings
from nova.security.secrets import KNOWN_SECRETS, SecretStore, ignored_legacy_env


def build_diagnostics(store: SecretStore | None = None) -> dict:
    """Build the diagnostics report. Safe to display and to export."""
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
            "reduce_motion": settings.ui.reduce_motion,
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
