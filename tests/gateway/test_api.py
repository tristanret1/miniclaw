"""Tests for bot.gateway.api — HTTP/WS API gateway."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from bot.gateway.api import create_api_app, _ws_clients


@pytest.fixture(autouse=True)
def _clean_ws():
    """Clear WS client set between tests."""
    _ws_clients.clear()
    yield
    _ws_clients.clear()


@pytest.fixture
async def api_client():
    """Create a test client for the API app (no auth)."""
    app = create_api_app(api_key="")
    async with TestClient(TestServer(app)) as client:
        yield client


@pytest.fixture
async def api_client_with_key():
    """Create a test client for the API app with API key auth."""
    app = create_api_app(api_key="test-secret")
    async with TestClient(TestServer(app)) as client:
        yield client


@pytest.mark.asyncio
async def test_get_agents(api_client):
    """GET /api/agents returns agent list."""
    with patch("bot.gateway.api._tracker") as mock_tracker:
        mock_tracker.get_all_statuses.return_value = {
            "bot1": {"status": "idle", "detail": "", "since": 0}
        }
        resp = await api_client.get("/api/agents")
        assert resp.status == 200
        data = await resp.json()
        assert len(data) == 1
        assert data[0]["id"] == "bot1"


@pytest.mark.asyncio
async def test_post_chat(api_client):
    """POST /api/chat routes to llm.reply and returns the response."""
    with patch("bot.llm.reply", new_callable=AsyncMock, return_value="Hello back!") as mock_reply:
        resp = await api_client.post(
            "/api/chat",
            json={"session_key": "pixeltown:agent1", "text": "hello"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["reply"] == "Hello back!"
        mock_reply.assert_called_once()


@pytest.mark.asyncio
async def test_post_chat_missing_fields(api_client):
    """POST /api/chat with missing fields returns 400."""
    resp = await api_client.post("/api/chat", json={})
    assert resp.status == 400


@pytest.mark.asyncio
async def test_api_key_auth_rejects_without_key(api_client_with_key):
    """When api_key is set, requests without X-API-Key are rejected."""
    resp = await api_client_with_key.get("/api/agents")
    assert resp.status == 401


@pytest.mark.asyncio
async def test_api_key_auth_accepts_correct_key(api_client_with_key):
    """When api_key is set, correct X-API-Key is accepted."""
    with patch("bot.gateway.api._tracker") as mock_tracker:
        mock_tracker.get_all_statuses.return_value = {}
        resp = await api_client_with_key.get(
            "/api/agents",
            headers={"X-API-Key": "test-secret"},
        )
        assert resp.status == 200
