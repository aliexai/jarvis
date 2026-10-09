"""FastAPI application: REST + WebSocket, bound to loopback only."""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from nova import __version__
from nova.api.auth import make_guard, token_matches
from nova.api.chat import stream_reply
from nova.api.state import CoreState

WINDOW_ACTIONS = frozenset({"minimize", "toggle-maximize", "close", "start-move"})
_message_ids = itertools.count(1)

WS_UNAUTHORIZED = 4401


def _model_for(state: CoreState) -> str:
    routing = state.settings.models.routing
    if routing == "strong":
        return state.settings.models.strong
    if routing == "fast":
        return state.settings.models.fast
    return state.settings.models.fast


async def _handle_message(websocket: WebSocket, state: CoreState, message: dict) -> None:
    kind = message.get("type")

    if kind == "ping":
        await websocket.send_json({"type": "pong"})
        return

    if kind == "chat.send":
        text = str(message.get("text") or "").strip()
        if not text:
            await websocket.send_json({"type": "chat.error", "data": {"message": "empty message"}})
            return
        await _stream_chat(websocket, state, text)
        return

    if kind == "settings.update":
        patch = message.get("patch") or {}
        try:
            state.update_settings(patch)
        except Exception as exc:
            await websocket.send_json({"type": "settings.error", "data": {"message": str(exc)}})
            return
        await websocket.send_json(
            {"type": "settings", "data": state.settings.model_dump(mode="json")}
        )
        return

    await websocket.send_json(
        {"type": "error", "data": {"message": f"unknown message type: {kind!r}"}}
    )


async def _stream_chat(websocket: WebSocket, state: CoreState, text: str) -> None:
    model = _model_for(state)
    message_id = f"m{next(_message_ids)}"

    await websocket.send_json({"type": "orb.state", "data": {"state": "thinking"}})
    await websocket.send_json(
        {"type": "chat.start", "data": {"id": message_id, "role": "assistant", "model": model}}
    )

    speaking = False
    async for chunk in stream_reply(text):
        if not speaking:
            speaking = True
            await websocket.send_json({"type": "orb.state", "data": {"state": "speaking"}})
        await websocket.send_json({"type": "chat.delta", "data": {"id": message_id, "text": chunk}})

    await websocket.send_json({"type": "chat.done", "data": {"id": message_id, "model": model}})
    await websocket.send_json({"type": "orb.state", "data": {"state": "idle"}})

    if state.audit is not None:
        state.audit.append(
            "user",
            "chat.send",
            target=model,
            decision="allow",
            detail=f"{len(text)} chars",
        )


def create_app(state: CoreState, static_dir: Path | None = None) -> FastAPI:
    """Build the FastAPI app for one session."""
    app = FastAPI(title="NOVA Core", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.core = state

    guard = Depends(make_guard(state.token))

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "core": "ready"}

    @app.get("/api/settings", dependencies=[guard])
    async def get_settings() -> dict[str, Any]:
        return state.settings.model_dump(mode="json")

    @app.put("/api/settings", dependencies=[guard])
    async def put_settings(patch: dict[str, Any]) -> dict[str, Any]:
        try:
            state.update_settings(patch)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid settings: {exc}") from exc
        return state.settings.model_dump(mode="json")

    @app.get("/api/secrets", dependencies=[guard])
    async def get_secrets() -> dict[str, Any]:
        return {
            "keyring_available": state.secrets.keyring_available,
            "secrets": state.secret_status(),
        }

    @app.get("/api/diagnostics", dependencies=[guard])
    async def get_diagnostics() -> dict[str, Any]:
        return state.diagnostics()

    @app.post("/api/window/{action}", dependencies=[guard])
    async def window_action(action: str) -> dict[str, Any]:
        if action not in WINDOW_ACTIONS:
            raise HTTPException(status_code=400, detail=f"unknown window action: {action}")
        if state.window_action is None:
            raise HTTPException(status_code=503, detail="no window attached")
        state.window_action(action)
        return {"ok": True, "action": action}

    @app.post("/api/ui/ready", dependencies=[guard])
    async def ui_ready() -> dict[str, Any]:
        state.ui_ready.set()
        state.log.info("UI reported ready")
        return {"ok": True}

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        if not token_matches(websocket.query_params.get("token"), state.token):
            await websocket.close(code=WS_UNAUTHORIZED)
            return
        await websocket.accept()
        await websocket.send_json(
            {
                "type": "hello",
                "data": {
                    "version": __version__,
                    "settings": state.settings.model_dump(mode="json"),
                },
            }
        )
        try:
            while True:
                message = await websocket.receive_json()
                await _handle_message(websocket, state, message)
        except WebSocketDisconnect:
            state.log.info("UI websocket disconnected")
        except Exception:
            state.log.exception("websocket error")

    if static_dir is not None and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="ui")
    else:

        @app.get("/")
        async def missing_ui() -> dict[str, Any]:
            return {
                "error": "UI bundle not found",
                "hint": "cd ui/web && npm install && npm run build",
            }

    return app
