"""The security policy engine.

Deny by default. Every capability the assistant can use is expressed as a
:class:`Permission`; the engine answers ALLOW, ASK (explicit user confirmation)
or DENY for a given resource, using the allowlists in the settings.

The engine is **fail-closed**: any error during evaluation becomes a DENY. Path
handling resolves symlinks and rejects anything that escapes an allowlisted
folder, so traversal (``..``) and symlink escapes are both blocked.
"""

from __future__ import annotations

import os
import re
import shlex
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from nova.config.settings import SecuritySettings
from nova.errors import PolicyError

# Characters that would allow command chaining, redirection or injection.
_SHELL_METACHARS = re.compile(r"[;&|<>`$\r\n]")


class Permission(StrEnum):
    FS_READ = "fs.read"
    FS_WRITE = "fs.write"
    FS_DELETE = "fs.delete"
    APP_LAUNCH = "app.launch"
    NET_FETCH = "net.fetch"
    SHELL_RUN = "shell.run"
    CLIPBOARD_READ = "clipboard.read"
    CLIPBOARD_WRITE = "clipboard.write"
    SCREEN_CAPTURE = "screen.capture"
    AUDIO_RECORD = "audio.record"
    SYSTEM_CONTROL = "system.control"
    SYSTEM_INFO = "system.info"


class Decision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    decision: Decision
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def requires_confirmation(self) -> bool:
        return self.decision is Decision.ASK


def resolve_within(base: Path, candidate: str | os.PathLike[str]) -> Path:
    """Resolve ``candidate`` and ensure it stays inside ``base``.

    Raises :class:`PolicyError` if the resolved path escapes ``base`` - this
    covers ``..`` traversal and symlinks pointing outside the root.
    """
    base_resolved = Path(base).expanduser().resolve(strict=False)
    target = Path(candidate).expanduser()
    if not target.is_absolute():
        target = base_resolved / target
    target_resolved = target.resolve(strict=False)
    try:
        target_resolved.relative_to(base_resolved)
    except ValueError as exc:
        raise PolicyError(f"path escapes allowed root: {candidate}") from exc
    return target_resolved


def resolve_within_any(folders: list[Path], candidate: str | os.PathLike[str]) -> Path:
    """Resolve against the first allowlisted folder that contains ``candidate``."""
    if not folders:
        raise PolicyError("no allowed folders configured")
    for folder in folders:
        try:
            return resolve_within(folder, candidate)
        except PolicyError:
            continue
    raise PolicyError(f"path is not within any allowed folder: {candidate}")


class PolicyEngine:
    """Evaluates permissions against the configured allowlists."""

    def __init__(self, settings: SecuritySettings) -> None:
        self._settings = settings

    @property
    def settings(self) -> SecuritySettings:
        return self._settings

    def allowed_folders(self) -> list[Path]:
        return [Path(p).expanduser() for p in self._settings.allowed_folders]

    # -- entry point -------------------------------------------------------
    def check(self, permission: Permission | str, resource: str | None = None) -> PolicyResult:
        """Return the decision for ``permission`` on ``resource`` (fail-closed)."""
        try:
            return self._evaluate(Permission(permission), resource)
        except PolicyError as exc:
            return PolicyResult(Decision.DENY, str(exc))
        except Exception:
            return PolicyResult(Decision.DENY, "policy evaluation failed (fail-closed)")

    # -- rules -------------------------------------------------------------
    def _evaluate(self, permission: Permission, resource: str | None) -> PolicyResult:
        if permission in (Permission.FS_READ, Permission.FS_WRITE, Permission.FS_DELETE):
            return self._check_fs(permission, resource)
        if permission is Permission.APP_LAUNCH:
            return self._check_app(resource)
        if permission is Permission.NET_FETCH:
            return self._check_domain(resource)
        if permission is Permission.SHELL_RUN:
            return self._check_shell(resource)
        if permission in (
            Permission.CLIPBOARD_READ,
            Permission.SCREEN_CAPTURE,
            Permission.AUDIO_RECORD,
        ):
            return PolicyResult(Decision.ASK, f"{permission.value} requires explicit confirmation")
        if permission in (Permission.CLIPBOARD_WRITE, Permission.SYSTEM_CONTROL):
            return PolicyResult(Decision.ALLOW, f"{permission.value} is permitted")
        if permission is Permission.SYSTEM_INFO:
            return PolicyResult(Decision.ALLOW, "reading local system information is permitted")
        return PolicyResult(Decision.DENY, f"unknown permission: {permission}")

    def _check_fs(self, permission: Permission, resource: str | None) -> PolicyResult:
        if not resource:
            return PolicyResult(Decision.DENY, "no path supplied")
        folders = self.allowed_folders()
        if not folders:
            return PolicyResult(Decision.DENY, "no allowed folders configured")
        resolve_within_any(folders, resource)  # raises PolicyError -> DENY
        if permission is Permission.FS_DELETE:
            return PolicyResult(Decision.ASK, "deleting files requires confirmation")
        return PolicyResult(Decision.ALLOW, f"{permission.value} within an allowed folder")

    def _check_app(self, resource: str | None) -> PolicyResult:
        if not resource:
            return PolicyResult(Decision.DENY, "no application specified")
        allowed = {entry.lower() for entry in self._settings.allowed_apps}
        name = Path(str(resource)).name.lower()
        if name.endswith(".exe"):
            name = name[:-4]
        if name in allowed or str(resource).lower() in allowed:
            return PolicyResult(Decision.ALLOW, f"application '{name}' is allowlisted")
        return PolicyResult(Decision.ASK, f"application '{name}' is not allowlisted")

    def _check_domain(self, resource: str | None) -> PolicyResult:
        if not resource:
            return PolicyResult(Decision.DENY, "no URL supplied")
        text = str(resource)
        host = urlparse(text).hostname
        if not host and "/" not in text:
            host = text  # allow a bare hostname such as "example.com"
        host = (host or "").lower()
        if not host:
            return PolicyResult(Decision.DENY, "unparseable URL")
        for entry in self._settings.allowed_domains:
            allowed = entry.lower().lstrip(".")
            if host == allowed or host.endswith("." + allowed):
                return PolicyResult(Decision.ALLOW, f"domain '{host}' is allowlisted")
        return PolicyResult(Decision.ASK, f"domain '{host}' is not allowlisted")

    def _check_shell(self, resource: str | None) -> PolicyResult:
        if not resource or not str(resource).strip():
            return PolicyResult(Decision.DENY, "empty command")
        text = str(resource)
        if _SHELL_METACHARS.search(text):
            return PolicyResult(Decision.DENY, "shell operators are not permitted")
        try:
            argv = shlex.split(text, posix=False)
        except ValueError as exc:
            return PolicyResult(Decision.DENY, f"unparseable command: {exc}")
        if not argv:
            return PolicyResult(Decision.DENY, "empty command")
        base = Path(argv[0]).name.lower()
        if base.endswith(".exe"):
            base = base[:-4]
        allowed = {entry.lower() for entry in self._settings.allowed_commands}
        if base in allowed:
            return PolicyResult(Decision.ALLOW, f"command '{base}' is allowlisted")
        return PolicyResult(Decision.ASK, f"command '{base}' is not allowlisted")
