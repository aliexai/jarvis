"""Shared state for the local API and the Qt shell."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from nova.budget import BudgetGuard
from nova.chat.service import ChatService
from nova.config import AppPaths, Settings, get_paths, load_settings, save_settings
from nova.diagnostics import build_diagnostics
from nova.errors import SecretError
from nova.logging_setup import get_logger
from nova.memory import ChatStore, Database, UsageStore
from nova.net import resolve_proxy
from nova.providers.base import LLMProvider
from nova.providers.gemini import GeminiProvider
from nova.providers.mock import MockProvider
from nova.providers.pricing import (
    PRICES_LAST_CHECKED,
    PRICES_SOURCE,
    PriceTable,
    builtin_table,
    load_price_table,
)
from nova.security import AuditLog, PolicyEngine, SecretStore
from nova.security.secrets import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    GEMINI_API_KEY,
    KNOWN_SECRETS,
)
from nova.tools import ToolRegistry, demo_registry


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

    # Phase 3: storage, tools, provider and the chat pipeline.
    db: Database | None = None
    store: ChatStore | None = None
    usage: UsageStore | None = None
    registry: ToolRegistry | None = None
    price_table: PriceTable = field(default_factory=builtin_table)
    policy: PolicyEngine | None = None
    chat: ChatService | None = None

    _provider: LLMProvider | None = field(default=None, repr=False)
    _provider_signature: tuple | None = field(default=None, repr=False)
    _closed: bool = field(default=False, repr=False)

    @property
    def log(self) -> Any:
        return get_logger("core")

    # -- construction ------------------------------------------------------
    @classmethod
    def create(
        cls,
        *,
        token: str,
        paths: AppPaths | None = None,
        settings: Settings | None = None,
        secrets: SecretStore | None = None,
        audit_path=None,
        db_path=None,
    ) -> CoreState:
        resolved_paths = (paths or get_paths()).ensure()
        resolved_settings = settings or load_settings(paths=resolved_paths)
        audit = AuditLog(audit_path or resolved_paths.audit_db)

        database = Database(db_path or resolved_paths.memory_db)
        state = cls(
            token=token,
            paths=resolved_paths,
            settings=resolved_settings,
            secrets=secrets or SecretStore(),
            audit=audit,
            db=database,
            store=ChatStore(database),
            usage=UsageStore(database),
            registry=demo_registry(),
            price_table=load_price_table(resolved_paths.config / "prices.json"),
            policy=PolicyEngine(resolved_settings.security),
        )
        state.chat = state._build_chat()
        audit.append("system", "app.start", target=str(resolved_paths.root), decision="info")
        return state

    def _build_chat(self) -> ChatService:
        if self.store is None or self.usage is None or self.registry is None or self.policy is None:
            raise RuntimeError("core state is not fully initialised")
        return ChatService(
            settings=lambda: self.settings,
            provider=self.provider,
            store=self.store,
            usage=self.usage,
            registry=self.registry,
            policy=self.policy,
            price_table=self.price_table,
        )

    # -- provider ----------------------------------------------------------
    def provider(self) -> LLMProvider:
        """Return the current provider, rebuilding it when relevant settings change."""
        settings = self.settings.provider
        signature = (
            settings.name,
            bool(self.secrets.get(GEMINI_API_KEY)),
            settings.proxy_mode,
            settings.proxy_url,
            settings.timeout_seconds,
            settings.max_retries,
        )
        if self._provider is None or self._provider_signature != signature:
            self._provider = self._build_provider()
            self._provider_signature = signature
        return self._provider

    def _build_provider(self) -> LLMProvider:
        settings = self.settings.provider
        if settings.name == "mock":
            self.log.info("using the mock provider")
            return MockProvider()
        decision = resolve_proxy(settings.proxy_mode, settings.proxy_url)
        self.log.info("gemini provider: proxy %s", decision.note)
        return GeminiProvider(
            self.secrets.get(GEMINI_API_KEY),
            proxy=decision,
            timeout_seconds=settings.timeout_seconds,
            max_retries=settings.max_retries,
        )

    # -- settings ----------------------------------------------------------
    def update_settings(self, patch: dict) -> Settings:
        """Merge a partial update, validate it, persist it and return it."""
        merged = deep_merge(self.settings.model_dump(mode="json"), patch)
        self.settings = Settings.model_validate(merged)
        save_settings(self.settings, paths=self.paths)

        # The policy engine snapshots the allowlists, so rebuild it.
        self.policy = PolicyEngine(self.settings.security)
        self.chat = self._build_chat()

        if self.audit is not None:
            self.audit.append(
                "user",
                "settings.update",
                target=",".join(sorted(patch.keys())) or None,
                decision="allow",
            )
        self.log.info("settings updated: %s", ", ".join(sorted(patch.keys())))
        return self.settings

    def budget_status(self) -> dict:
        if self.usage is None:
            return {}
        return BudgetGuard(self.usage, self.settings.limits).status().to_dict()

    # -- reporting ---------------------------------------------------------
    def diagnostics(self) -> dict:
        report = build_diagnostics(store=self.secrets)
        provider_settings = self.settings.provider
        decision = resolve_proxy(provider_settings.proxy_mode, provider_settings.proxy_url)

        report["core"] = {
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "ui_ready": self.ui_ready.is_set(),
        }
        report["provider"] = {
            "name": provider_settings.name,
            "models": {
                "fast": self.settings.models.fast,
                "strong": self.settings.models.strong,
                "routing": self.settings.models.routing,
            },
            "tools_enabled": provider_settings.tools_enabled,
        }
        report["network"] = {
            "proxy_mode": decision.mode,
            "detected": decision.detected,
            "effective": decision.effective_url,
            "supported": decision.supported,
            "note": decision.note,
        }
        report["pricing"] = {
            "tier": self.settings.pricing.tier,
            "last_checked": self.price_table.last_checked,
            "source": self.price_table.source,
            "builtin_last_checked": PRICES_LAST_CHECKED,
            "builtin_source": PRICES_SOURCE,
            "models_priced": len(self.price_table.models),
        }
        report["tools"] = self.registry.names() if self.registry else []
        report["budget"] = self.budget_status()
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

    # -- secrets -----------------------------------------------------------
    def set_secret(self, name: str, value: str) -> None:
        """Persist a secret and force the provider to pick it up immediately."""
        if name not in KNOWN_SECRETS:
            raise SecretError(f"unknown secret: {name}")
        self.secrets.set(name, value)
        self._provider = None
        self._provider_signature = None
        if self.audit is not None:
            self.audit.append("user", "secret.update", target=name, decision="allow")

    def delete_secret(self, name: str) -> None:
        """Remove a stored secret and rebuild the provider."""
        if name not in KNOWN_SECRETS:
            raise SecretError(f"unknown secret: {name}")
        self.secrets.delete(name)
        self._provider = None
        self._provider_signature = None
        if self.audit is not None:
            self.audit.append("user", "secret.delete", target=name, decision="allow")

    def make_voice_service(self) -> Any:
        """Build a voice pipeline bound to the current settings and chat service."""
        from nova.voice import VoiceService
        from nova.voice.capture import MicCapture
        from nova.voice.stt import Transcriber
        from nova.voice.tts import Speaker

        voice = self.settings.voice
        return VoiceService(
            chat=lambda: self.chat,
            capture_factory=MicCapture,
            transcriber=Transcriber(model_size=voice.stt_model, language=voice.language),
            speaker=Speaker(
                api_key=self.secrets.get(ELEVENLABS_API_KEY),
                voice_id=self.secrets.get(ELEVENLABS_VOICE_ID),
                provider=voice.tts_provider,
            ),
        )

    def brain_status(self) -> dict:
        """Whether chat can answer for real, run in demo mode, or needs a key."""
        provider = self.settings.provider.name
        has_gemini = self.secrets.has(GEMINI_API_KEY)
        if provider == "mock":
            mode = "demo"
        elif has_gemini:
            mode = "live"
        else:
            mode = "needs_key"
        return {
            "mode": mode,
            "provider": provider,
            "has_gemini_key": has_gemini,
            "has_elevenlabs_key": self.secrets.has(ELEVENLABS_API_KEY),
        }

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
        if self.db is not None:
            try:
                self.db.close()
            except Exception:
                self.log.warning("could not close the local database cleanly")
