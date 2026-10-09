"""Tests for path resolution and portable mode."""

from __future__ import annotations

from nova.config.paths import env_flag, get_paths


def test_portable_paths_live_under_base(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_DIR", str(tmp_path))
    paths = get_paths(portable=True)
    assert paths.root == tmp_path / ".data"
    assert paths.settings_file == tmp_path / ".data" / "config" / "settings.json"
    assert paths.log_file == tmp_path / ".data" / "logs" / "nova.log"


def test_env_flag_parsing(monkeypatch):
    monkeypatch.setenv("NOVA_FLAG", "yes")
    assert env_flag("NOVA_FLAG") is True
    monkeypatch.setenv("NOVA_FLAG", "0")
    assert env_flag("NOVA_FLAG") is False
    monkeypatch.delenv("NOVA_FLAG", raising=False)
    assert env_flag("NOVA_FLAG") is False
    assert env_flag("NOVA_FLAG", True) is True


def test_ensure_creates_every_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_PORTABLE_DIR", str(tmp_path))
    paths = get_paths(portable=True).ensure()
    assert paths.root.is_dir()
    assert paths.data.is_dir()
    assert paths.config.is_dir()
    assert paths.cache.is_dir()
    assert paths.logs.is_dir()
