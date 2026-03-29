"""Tests for PixelTownGateway — unit tests with mocked aiohttp."""

import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add src/ to import path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from status import AgentStatusTracker


# We need to mock aiohttp before importing gateway
@pytest.fixture(autouse=True)
def mock_aiohttp():
    """Mock aiohttp.web so gateway can be imported without the real package."""
    mock_web = MagicMock()
    mock_web.WebSocketResponse = MagicMock
    mock_web.WSMsgType = MagicMock()
    mock_web.WSMsgType.TEXT = 1
    mock_web.WSMsgType.ERROR = 2
    mock_web.Application = MagicMock
    mock_web.AppRunner = MagicMock
    mock_web.TCPSite = MagicMock
    mock_web.Request = MagicMock
    mock_web.Response = MagicMock
    mock_web.json_response = lambda data: {"json": data}
    with patch.dict(sys.modules, {"aiohttp": MagicMock(web=mock_web), "aiohttp.web": mock_web}):
        yield mock_web


@pytest.fixture
def tracker():
    return AgentStatusTracker(["agent-1", "agent-2"])


@pytest.fixture
def gateway(tracker, tmp_path):
    from gateway_pixeltown import PixelTownGateway

    return PixelTownGateway(
        tracker,
        host="127.0.0.1",
        port=8765,
        static_dir=str(tmp_path / "dist"),
        layout_file=str(tmp_path / "layout.json"),
    )


def test_gateway_creates_with_tracker(gateway, tracker):
    assert gateway._tracker is tracker


def test_build_agents_list(gateway, tracker):
    tracker.on_working("agent-1", "busy")
    agents = gateway._build_agents_list()
    assert len(agents) == 2
    a1 = next(a for a in agents if a["id"] == "agent-1")
    assert a1["status"] == "working"
    assert a1["detail"] == "busy"


def test_load_layout_empty(gateway):
    assert gateway._load_layout() == []


def test_save_and_load_layout(gateway, tmp_path):
    buildings = [{"id": "cottage-1", "x": 3, "y": 3}]
    gateway._save_layout(buildings)
    loaded = gateway._load_layout()
    assert loaded == buildings


def test_current_season_returns_valid():
    from gateway_pixeltown import PixelTownGateway

    season = PixelTownGateway._current_season()
    assert season in ("spring", "summer", "autumn", "winter")


def test_status_change_listener_registered(tracker, gateway):
    """Gateway registers itself as a status listener."""
    assert gateway._on_status_change in tracker._listeners


@pytest.mark.asyncio
async def test_on_status_change_broadcasts(gateway, tracker):
    """When status changes, gateway pushes to WS clients."""
    mock_ws = MagicMock()
    mock_ws.closed = False
    mock_ws.send_json = AsyncMock()
    gateway._ws_clients.add(mock_ws)

    tracker.on_working("agent-1", "test task")
    # Let the created task run
    await asyncio.sleep(0)
    mock_ws.send_json.assert_called_once()
    call_data = mock_ws.send_json.call_args[0][0]
    assert call_data["type"] == "agent_status"
    assert call_data["agent"] == "agent-1"
    assert call_data["status"] == "working"
