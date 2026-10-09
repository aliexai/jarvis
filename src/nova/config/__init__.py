"""Configuration: paths, typed settings and schema migrations."""

from __future__ import annotations

from nova.config.migrations import SCHEMA_VERSION, migrate
from nova.config.paths import AppPaths, env_flag, get_paths
from nova.config.settings import (
    ApiSettings,
    LimitSettings,
    ModelSettings,
    SecuritySettings,
    Settings,
    UiSettings,
    VoiceSettings,
    load_settings,
    save_settings,
)

__all__ = [
    "SCHEMA_VERSION",
    "ApiSettings",
    "AppPaths",
    "LimitSettings",
    "ModelSettings",
    "SecuritySettings",
    "Settings",
    "UiSettings",
    "VoiceSettings",
    "env_flag",
    "get_paths",
    "load_settings",
    "migrate",
    "save_settings",
]
