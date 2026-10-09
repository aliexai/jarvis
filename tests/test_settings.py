"""Tests for the settings schema, persistence and migrations."""

from __future__ import annotations

import json

import pytest

from nova.config.migrations import SCHEMA_VERSION
from nova.config.settings import load_settings, save_settings
from nova.errors import ConfigError


def test_defaults_when_file_missing(tmp_path):
    settings = load_settings(tmp_path / "settings.json")
    assert settings.version == SCHEMA_VERSION
    assert settings.ui.theme == "cyan"
    assert settings.models.fast
    assert settings.models.strong
    assert "python" in settings.security.allowed_commands


def test_save_load_roundtrip(tmp_path):
    file = tmp_path / "settings.json"
    settings = load_settings(file)
    settings.ui.theme = "crimson"
    settings.security.allowed_folders.append(str(tmp_path))
    save_settings(settings, file)

    reloaded = load_settings(file)
    assert reloaded.ui.theme == "crimson"
    assert str(tmp_path) in reloaded.security.allowed_folders
    # Atomic write must not leave temp files behind.
    assert [p.name for p in tmp_path.iterdir()] == ["settings.json"]


def test_migration_bumps_old_version(tmp_path):
    file = tmp_path / "settings.json"
    file.write_text(json.dumps({"version": 0, "log_level": "DEBUG"}), encoding="utf-8")
    settings = load_settings(file)
    assert settings.version == SCHEMA_VERSION
    assert settings.log_level == "DEBUG"  # existing values survive migration


def test_invalid_settings_raise_config_error(tmp_path):
    file = tmp_path / "settings.json"
    file.write_text(json.dumps({"ui": {"theme": "purple"}}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_settings(file)


def test_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("NOVA_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("NOVA_THEME", "emerald")
    monkeypatch.setenv("NOVA_API_PORT", "8765")
    settings = load_settings(tmp_path / "settings.json")
    assert settings.log_level == "WARNING"
    assert settings.ui.theme == "emerald"
    assert settings.api.port == 8765
