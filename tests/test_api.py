"""Tests for the local API: authentication, settings, secrets and chat."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nova.api.app import create_app
from nova.config import load_settings
from nova.security.secrets import GEMINI_API_KEY

TOKEN = "test-token"


@pytest.fixture
def client(core_state):
    app = create_app(core_state, static_dir=None)
    with TestClient(app) as test_client:
        yield test_client


# -- authentication --------------------------------------------------------


def test_health_needs_no_token(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_settings_requires_token(client):
    assert client.get("/api/settings").status_code == 401


def test_settings_rejects_wrong_token(client):
    assert client.get("/api/settings?token=nope").status_code == 401


def test_token_accepted_from_header(client):
    response = client.get("/api/settings", headers={"X-Nova-Token": TOKEN})
    assert response.status_code == 200


# -- settings --------------------------------------------------------------


def test_get_settings_shape(client):
    body = client.get(f"/api/settings?token={TOKEN}").json()
    assert body["ui"]["theme"] in {"cyan", "emerald", "crimson"}
    assert "models" in body


def test_put_settings_persists(client, core_state):
    response = client.put(f"/api/settings?token={TOKEN}", json={"ui": {"theme": "crimson"}})
    assert response.status_code == 200
    assert response.json()["ui"]["theme"] == "crimson"

    reloaded = load_settings(paths=core_state.paths)
    assert reloaded.ui.theme == "crimson"


def test_put_settings_rejects_invalid_value(client):
    response = client.put(f"/api/settings?token={TOKEN}", json={"ui": {"theme": "purple"}})
    assert response.status_code == 400


# -- secrets ---------------------------------------------------------------


def test_secret_status_masks_values(client, core_state):
    core_state.secrets.set(GEMINI_API_KEY, "AIzaSyABCDEFGHIJKLMNOP1234567890")

    response = client.get(f"/api/secrets?token={TOKEN}")
    assert response.status_code == 200
    body = response.json()

    entry = body["secrets"][GEMINI_API_KEY]
    assert entry["masked"].startswith("(set,")
    assert entry["prefix_ok"] is True
    assert "AIzaSy" not in json.dumps(body)


# -- diagnostics -----------------------------------------------------------


def test_diagnostics_has_paths_and_no_key_material(client, core_state):
    core_state.secrets.set(GEMINI_API_KEY, "opaque-secret-value-123456")

    body = client.get(f"/api/diagnostics?token={TOKEN}").json()
    assert "paths" in body
    assert body["secrets"][GEMINI_API_KEY]["source"] == "keyring"
    assert "opaque-secret-value-123456" not in json.dumps(body)


# -- window actions --------------------------------------------------------


def test_window_action_invokes_bridge(client, core_state):
    seen: list[str] = []
    core_state.window_action = seen.append

    response = client.post(f"/api/window/minimize?token={TOKEN}")
    assert response.status_code == 200
    assert seen == ["minimize"]


def test_window_action_unknown_is_rejected(client):
    assert client.post(f"/api/window/explode?token={TOKEN}").status_code == 400


def test_window_action_without_window_is_unavailable(client):
    assert client.post(f"/api/window/close?token={TOKEN}").status_code == 503


def test_ui_ready_is_recorded(client, core_state):
    assert core_state.ui_ready.is_set() is False
    assert client.post(f"/api/ui/ready?token={TOKEN}").status_code == 200
    assert core_state.ui_ready.is_set() is True


# -- websocket -------------------------------------------------------------


def test_websocket_rejects_bad_token(client):
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect("/ws?token=wrong") as websocket,
    ):
        websocket.receive_json()


def test_websocket_streams_mock_chat(client):
    with client.websocket_connect(f"/ws?token={TOKEN}") as websocket:
        hello = websocket.receive_json()
        assert hello["type"] == "hello"
        assert "settings" in hello["data"]
        assert "budget" in hello["data"]

        websocket.send_json({"type": "chat.send", "text": "write me a python function"})

        seen: list[str] = []
        text = ""
        while True:
            message = websocket.receive_json()
            seen.append(message["type"])
            if message["type"] == "chat.delta":
                text += message["data"]["text"]
            if message["type"] in ("chat.done", "chat.error"):
                break

    assert "chat.start" in seen
    assert "chat.delta" in seen
    assert "chat.usage" in seen
    assert "```python" in text


def test_websocket_reports_error_without_chat_done(client, core_state):
    """A failing provider must surface chat.error, never hang the stream."""
    from nova.providers.errors import AuthError
    from nova.providers.mock import MockProvider

    failing = MockProvider(fail_with=AuthError("no key"))
    core_state.provider = lambda: failing  # type: ignore[method-assign]
    core_state.chat = core_state._build_chat()

    with client.websocket_connect(f"/ws?token={TOKEN}") as websocket:
        websocket.receive_json()  # hello
        websocket.send_json({"type": "chat.send", "text": "explain list versus tuple"})

        kinds: list[str] = []
        while True:
            message = websocket.receive_json()
            kinds.append(message["type"])
            if message["type"] in ("chat.done", "chat.error"):
                break

    assert "chat.error" in kinds


def test_websocket_rejects_empty_message(client):
    with client.websocket_connect(f"/ws?token={TOKEN}") as websocket:
        websocket.receive_json()  # hello
        websocket.send_json({"type": "chat.send", "text": "   "})
        message = websocket.receive_json()
        assert message["type"] == "chat.error"


def test_websocket_answers_time_locally(client):
    with client.websocket_connect(f"/ws?token={TOKEN}") as websocket:
        websocket.receive_json()  # hello
        websocket.send_json({"type": "chat.send", "text": "what time is it?"})

        model = None
        while True:
            message = websocket.receive_json()
            if message["type"] == "chat.start":
                model = message["data"]["model"]
            if message["type"] in ("chat.done", "chat.error"):
                break

    assert model == "local"


def test_websocket_updates_settings(client, core_state):
    with client.websocket_connect(f"/ws?token={TOKEN}") as websocket:
        websocket.receive_json()  # hello
        websocket.send_json({"type": "settings.update", "patch": {"ui": {"reduce_motion": True}}})
        message = websocket.receive_json()
        assert message["type"] == "settings"
        assert message["data"]["ui"]["reduce_motion"] is True

    assert load_settings(paths=core_state.paths).ui.reduce_motion is True
