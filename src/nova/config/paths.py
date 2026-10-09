"""Filesystem locations for NOVA.

Two modes are supported:

* **installed** (default) - everything lives under the per-user directories
  reported by ``platformdirs`` (on Windows: ``%LOCALAPPDATA%\\Nova``).
* **portable** - everything lives under a single directory next to the app,
  selected with ``NOVA_PORTABLE=1`` (optionally ``NOVA_PORTABLE_DIR=<path>``).
  Useful for a USB stick or a self-contained test run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

APP_NAME = "Nova"


def env_flag(name: str, default: bool = False) -> bool:
    """Read a boolean from the environment (``1/true/yes/on``)."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppPaths:
    """Resolved directories and well-known files for a running instance."""

    root: Path
    data: Path
    config: Path
    cache: Path
    logs: Path

    @property
    def settings_file(self) -> Path:
        return self.config / "settings.json"

    @property
    def audit_db(self) -> Path:
        return self.data / "audit.db"

    @property
    def memory_db(self) -> Path:
        return self.data / "memory.db"

    @property
    def log_file(self) -> Path:
        return self.logs / "nova.log"

    def ensure(self) -> AppPaths:
        """Create every directory. Safe to call repeatedly."""
        for directory in (self.root, self.data, self.config, self.cache, self.logs):
            directory.mkdir(parents=True, exist_ok=True)
        return self


def get_paths(portable: bool | None = None) -> AppPaths:
    """Return the active :class:`AppPaths` for this process."""
    if portable is None:
        portable = env_flag("NOVA_PORTABLE", False)

    if portable:
        base = Path(os.environ.get("NOVA_PORTABLE_DIR") or os.getcwd()).resolve()
        root = base / ".data"
        return AppPaths(
            root=root,
            data=root / "data",
            config=root / "config",
            cache=root / "cache",
            logs=root / "logs",
        )

    dirs = PlatformDirs(APP_NAME, appauthor=False, roaming=False)
    data = Path(dirs.user_data_dir)
    return AppPaths(
        root=data,
        data=data,
        config=Path(dirs.user_config_dir),
        cache=Path(dirs.user_cache_dir),
        logs=Path(dirs.user_log_dir),
    )
