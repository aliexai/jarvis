"""Tests for the security policy engine."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from nova.config.settings import SecuritySettings
from nova.errors import PolicyError
from nova.security.policy import (
    Decision,
    Permission,
    PolicyEngine,
    resolve_within,
    resolve_within_any,
)


@pytest.fixture
def engine(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    settings = SecuritySettings(
        allowed_folders=[str(workspace)],
        allowed_apps=["notepad", "calc"],
        allowed_domains=["example.com", "trusted.org"],
        allowed_commands=["python", "git"],
    )
    return PolicyEngine(settings), workspace


def test_fs_read_inside_allowed_folder(engine):
    policy, workspace = engine
    assert policy.check(Permission.FS_READ, str(workspace / "notes.txt")).decision is Decision.ALLOW


def test_fs_write_outside_allowed_folder_is_denied(engine):
    policy, _ = engine
    result = policy.check(Permission.FS_WRITE, "C:/Windows/System32/drivers/etc/hosts")
    assert result.decision is Decision.DENY


def test_directory_traversal_is_denied(engine):
    policy, workspace = engine
    result = policy.check(Permission.FS_READ, str(workspace / ".." / "secret.txt"))
    assert result.decision is Decision.DENY


def test_delete_requires_confirmation(engine):
    policy, workspace = engine
    assert policy.check(Permission.FS_DELETE, str(workspace / "a.txt")).decision is Decision.ASK


def test_no_allowed_folders_denies_everything(tmp_path):
    policy = PolicyEngine(SecuritySettings())
    assert policy.check(Permission.FS_READ, str(tmp_path / "x")).decision is Decision.DENY


def test_app_allowlist(engine):
    policy, _ = engine
    assert policy.check(Permission.APP_LAUNCH, "notepad.exe").decision is Decision.ALLOW
    assert policy.check(Permission.APP_LAUNCH, "totally-unknown").decision is Decision.ASK


def test_domain_allowlist(engine):
    policy, _ = engine
    assert policy.check(Permission.NET_FETCH, "https://example.com/page").decision is Decision.ALLOW
    assert policy.check(Permission.NET_FETCH, "https://sub.trusted.org").decision is Decision.ALLOW
    assert policy.check(Permission.NET_FETCH, "https://evil.example.net").decision is Decision.ASK


def test_shell_operators_are_denied(engine):
    policy, _ = engine
    assert policy.check(Permission.SHELL_RUN, "git status && rm -rf /").decision is Decision.DENY
    assert policy.check(Permission.SHELL_RUN, "git status | more").decision is Decision.DENY
    assert policy.check(Permission.SHELL_RUN, "git log > out.txt").decision is Decision.DENY


def test_shell_allowlist(engine):
    policy, _ = engine
    assert policy.check(Permission.SHELL_RUN, "python -m pytest").decision is Decision.ALLOW
    assert policy.check(Permission.SHELL_RUN, "powershell -c ls").decision is Decision.ASK


def test_sensitive_permissions_require_confirmation(engine):
    policy, _ = engine
    sensitive = (
        Permission.CLIPBOARD_READ,
        Permission.SCREEN_CAPTURE,
        Permission.AUDIO_RECORD,
    )
    for permission in sensitive:
        assert policy.check(permission).decision is Decision.ASK


def test_unknown_permission_fails_closed(engine):
    policy, _ = engine
    assert policy.check("bogus.permission").decision is Decision.DENY


def test_resolve_within_rejects_escape(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    with pytest.raises(PolicyError):
        resolve_within(base, base / ".." / "outside.txt")


def test_resolve_within_accepts_nested(tmp_path):
    base = tmp_path / "base"
    nested = base / "a" / "b"
    nested.mkdir(parents=True)
    assert resolve_within(base, nested / "file.txt") == (nested / "file.txt").resolve()


def test_resolve_within_any_requires_a_match(tmp_path):
    with pytest.raises(PolicyError):
        resolve_within_any([], tmp_path / "x")


def _make_directory_link(link: Path, target: Path) -> bool:
    """Create a directory link, preferring a symlink and falling back to a
    Windows junction (which requires no elevation)."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return True
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0 and link.exists()
    return False


def test_symlink_escape_is_denied(tmp_path):
    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("top secret", encoding="utf-8")

    link = workspace / "link"
    if not _make_directory_link(link, outside):
        pytest.skip("no symlink or junction support on this host")

    # Sanity: the link really does point outside the allowed folder.
    assert link.resolve() == outside.resolve()

    policy = PolicyEngine(SecuritySettings(allowed_folders=[str(workspace)]))
    result = policy.check(Permission.FS_READ, str(link / "secret.txt"))
    assert result.decision is Decision.DENY
