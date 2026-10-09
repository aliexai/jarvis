"""Shared state for the local API and the Qt shell."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nova.config import AppPaths, Settings, get_paths, load_settings, save_settings
from nova.diagnostics import build_diagnostics
from nova.logging_setup import get_logger
from nova.security import AuditLog, SecretStore
from nova.security.secrets import KNOWN_SECRETS


def deep_merge(base: dict, patch: dict) -> dict:
    """Recursively merge ``patch`` into ``base`` (mutating and returning base)."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


@dataclass
class CoreState:
    """Owns the mutable core objects shared between the API and the UI."""

    token: str
    paths: AppPaths
    settings: Settings
    secrets: SecretStore
    audit: AuditLog | None = None
    # Set by the Qt shell: a thread-safe callable that performs window actions.
    window_action: Callable[[str], None] | None = None
    ui_ready: threading.Event = field(default_factory=threading.Event)
    started_at: float = field(default_factory=time.time)
    _closed: bool = field(default=False, repr=False)

    @property
    def log(self) -> Any:
        return get_logger("core")

    @classmethod
    def create(
        cls,
        *,
        token: str,
        paths: AppPaths | None = None,
        settings: Settings | None = None,
        secrets: SecretStore | None = None,
        audit_path=None,
    ) -> CoreState:
        resolved_paths = (paths or get_paths()).ensure()
        resolved_settings = settings or load_settings(paths=resolved_paths)
        audit = AuditLog(audit_path or resolved_paths.audit_db)
        state = cls(
            token=token,
            paths=resolved_paths,
            settings=resolved_settings,
            secrets=secrets or SecretStore(),
            audit=audit,
        )
        audit.append("system", "app.start", target=str(resolved_paths.root), decision="info")
        return state

    # -- settings ----------------------------------------------------------
    def update_settings(self, patch: dict) -> Settings:
        """Merge a partial update, validate it, persist it and return it."""
        merged = deep_merge(self.settings.model_dump(mode="json"), patch)
        self.settings = Settings.model_validate(merged)
        save_settings(self.settings, paths=self.paths)
        if self.audit is not None:
            self.audit.append(
                "user",
                "settings.update",
                target=",".join(sorted(patch.keys())) or None,
                decision="allow",
            )
        self.log.info("settings updated: %s", ", ".join(sorted(patch.keys())))
        return self.settings

    # -- reporting ---------------------------------------------------------
    def diagnostics(self) -> dict:
        report = build_diagnostics(store=self.secrets)
        report["core"] = {
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "ui_ready": self.ui_ready.is_set(),
        }
        return report

    def secret_status(self) -> dict[str, dict]:
        """Per-secret source and masked status. Never returns key material."""
        status: dict[str, dict] = {}
        for name in KNOWN_SECRETS:
            resolved = self.secrets.resolve(name)
            ok, _ = resolved.prefix_check()
            status[name] = {
                "source": resolved.source,
                "masked": resolved.masked,
                "prefix_ok": ok,
            }
        return status

    def close(self) -> None:
        """Release resources. Idempotent: safe to call from more than one path."""
        if self._closed:
            return
        self._closed = True
        if self.audit is not None:
            try:
                self.audit.append("system", "app.stop", decision="info")
            except Exception:
                self.log.warning("could not append the shutdown audit entry")
            self.audit.close()
