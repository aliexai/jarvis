"""Typed settings for NOVA.

The on-disk document is JSON (see :mod:`nova.config.paths`) and is validated by
Pydantic. A handful of scalar values can also be overridden by environment
variables (``NOVA_*``) for development; secrets are *never* stored here - they
live in the secret store (:mod:`nova.security.secrets`).
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from nova.config.migrations import SCHEMA_VERSION, migrate
from nova.config.paths import AppPaths, get_paths
from nova.errors import ConfigError


class ApiSettings(BaseModel):
    """Local-only API surface. Bound to loopback with a per-session token."""

    host: str = "127.0.0.1"
    # 0 means "pick a free port at startup"; the chosen port is never fixed.
    port: int = 0


class ModelSettings(BaseModel):
    """LLM routing. Model ids are configurable; no name is hardcoded elsewhere."""

    fast: str = "gemini-3.5-flash-lite"
    strong: str = "gemini-3.8-flash"
    routing: Literal["auto", "fast", "strong"] = "auto"


class VoiceSettings(BaseModel):
    tts_provider: Literal["auto", "elevenlabs", "sapi"] = "auto"
    tts_model: str = "eleven_flash_v2_5"
    tts_fallback_model: str = "eleven_multilingual_v2"
    stt_engine: Literal["local", "elevenlabs"] = "local"
    stt_model: Literal["tiny", "base", "small"] = "base"
    language: str = "en"
    wake_word_enabled: bool = False


class LimitSettings(BaseModel):
    """Soft cost limits. ``hard_stop`` blocks the call when a limit is hit."""

    daily_usd: float = 1.0
    monthly_usd: float = 10.0
    hard_stop: bool = True


class SecuritySettings(BaseModel):
    """Allowlists managed from Settings. The policy engine denies by default."""

    allowed_folders: list[str] = Field(default_factory=list)
    allowed_apps: list[str] = Field(default_factory=list)
    allowed_domains: list[str] = Field(default_factory=list)
    allowed_commands: list[str] = Field(
        default_factory=lambda: ["python", "pip", "node", "npm", "git", "pytest"]
    )


class UiSettings(BaseModel):
    theme: Literal["cyan", "emerald", "crimson"] = "cyan"
    accent: str = "#22d3ee"
    performance_mode: bool = False
    reduce_motion: bool = False


class Settings(BaseModel):
    """The full persisted configuration document."""

    version: int = SCHEMA_VERSION
    log_level: str = "INFO"
    memory_enabled: bool = True

    ui: UiSettings = Field(default_factory=UiSettings)
    api: ApiSettings = Field(default_factory=ApiSettings)
    models: ModelSettings = Field(default_factory=ModelSettings)
    voice: VoiceSettings = Field(default_factory=VoiceSettings)
    limits: LimitSettings = Field(default_factory=LimitSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)


class EnvOverrides(BaseSettings):
    """Scalar overrides read from ``NOVA_*`` environment variables (dev only)."""

    model_config = SettingsConfigDict(env_prefix="NOVA_", extra="ignore")

    log_level: str | None = None
    theme: Literal["cyan", "emerald", "crimson"] | None = None
    performance_mode: bool | None = None
    api_port: int | None = None


def _settings_path(path: Path | None, paths: AppPaths | None) -> Path:
    if path is not None:
        return path
    override = os.environ.get("NOVA_CONFIG_FILE")
    if override:
        return Path(override)
    return (paths or get_paths()).settings_file


def _apply_env_overrides(settings: Settings) -> None:
    env = EnvOverrides()
    if env.log_level is not None:
        settings.log_level = env.log_level
    if env.theme is not None:
        settings.ui.theme = env.theme
    if env.performance_mode is not None:
        settings.ui.performance_mode = env.performance_mode
    if env.api_port is not None:
        settings.api.port = env.api_port


def load_settings(path: Path | None = None, *, paths: AppPaths | None = None) -> Settings:
    """Load, migrate and validate settings; fall back to defaults if absent."""
    file = _settings_path(path, paths)

    raw: dict = {}
    if file.exists():
        try:
            raw = json.loads(file.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"could not read settings file {file}: {exc}") from exc

    try:
        settings = Settings.model_validate(migrate(raw))
    except Exception as exc:  # pydantic ValidationError -> ConfigError
        raise ConfigError(f"invalid settings in {file}: {exc}") from exc

    _apply_env_overrides(settings)
    return settings


def save_settings(
    settings: Settings, path: Path | None = None, *, paths: AppPaths | None = None
) -> Path:
    """Atomically write settings to disk and return the file path."""
    file = _settings_path(path, paths)
    file.parent.mkdir(parents=True, exist_ok=True)
    payload = settings.model_dump(mode="json")

    fd, tmp_name = tempfile.mkstemp(dir=str(file.parent), prefix=".settings-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, file)
    finally:
        tmp.unlink(missing_ok=True)
    return file
