# PixelTown Separation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate PixelTown into a standalone project, add a generic HTTP/WS API gateway to miniclaw, and remove all direct pixeltown coupling from miniclaw.

**Architecture:** miniclaw exposes a lightweight HTTP/WS API (`bot/gateway/api.py`) for external consumers. PixelTown becomes a fully independent project at `/Users/sen/side_project/pixeltown/` that communicates with miniclaw exclusively over HTTP/WebSocket. A new `bot/hooks.py` module replaces hardcoded pixeltown imports in `client.py` with a generic callback system.

**Tech Stack:** Python 3.13+, aiohttp, pytest, TypeScript/Vite/PixiJS (frontend, unchanged)

---

### Task 1: Create `bot/hooks.py` — Agent lifecycle hook registry

**Files:**
- Create: `bot/hooks.py`
- Test: `tests/test_hooks.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_hooks.py`:

```python
"""Tests for bot.hooks — agent lifecycle hook registry."""

from bot import hooks


def test_fire_working_calls_registered_callbacks():
    calls = []
    hooks.register_on_working(lambda aid, detail: calls.append((aid, detail)))
    hooks.fire_working("agent-1", "busy")
    assert calls == [("agent-1", "busy")]


def test_fire_idle_calls_registered_callbacks():
    calls = []
    hooks.register_on_idle(lambda aid: calls.append(aid))
    hooks.fire_idle("agent-1")
    assert calls == ["agent-1"]


def test_fire_working_ignores_callback_errors():
    def bad_cb(aid, detail):
        raise RuntimeError("boom")
    hooks.register_on_working(bad_cb)
    # Should not raise
    hooks.fire_working("agent-1", "test")


def test_fire_idle_ignores_callback_errors():
    def bad_cb(aid):
        raise RuntimeError("boom")
    hooks.register_on_idle(bad_cb)
    hooks.fire_idle("agent-1")


def test_multiple_callbacks_all_called():
    calls_a, calls_b = [], []
    hooks.register_on_working(lambda aid, d: calls_a.append(aid))
    hooks.register_on_working(lambda aid, d: calls_b.append(aid))
    hooks.fire_working("x", "")
    assert len(calls_a) == 1
    assert len(calls_b) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest tests/test_hooks.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.hooks'`

- [ ] **Step 3: Write minimal implementation**

Create `bot/hooks.py`:

```python
"""Agent lifecycle hooks — generic callback registry.

Replaces hardcoded gateway imports in client.py. Any gateway
(API, PixelTown, etc.) can register callbacks to receive agent
status changes.
"""

from __future__ import annotations

from typing import Callable

_on_working: list[Callable[[str, str], None]] = []
_on_idle: list[Callable[[str], None]] = []


def register_on_working(cb: Callable[[str, str], None]) -> None:
    """Register callback for agent-starts-working events. Args: (agent_id, detail)."""
    _on_working.append(cb)


def register_on_idle(cb: Callable[[str], None]) -> None:
    """Register callback for agent-becomes-idle events. Args: (agent_id,)."""
    _on_idle.append(cb)


def fire_working(agent_id: str, detail: str = "") -> None:
    """Notify all listeners that an agent started working."""
    for cb in _on_working:
        try:
            cb(agent_id, detail)
        except Exception:
            pass


def fire_idle(agent_id: str) -> None:
    """Notify all listeners that an agent became idle."""
    for cb in _on_idle:
        try:
            cb(agent_id)
        except Exception:
            pass


def _reset() -> None:
    """Clear all registered hooks. For testing only."""
    _on_working.clear()
    _on_idle.clear()
```

- [ ] **Step 4: Add `_reset()` to test fixture**

Add an autouse fixture to `tests/test_hooks.py` to prevent cross-test leakage:

```python
import pytest

@pytest.fixture(autouse=True)
def _clean_hooks():
    """Reset hooks between tests."""
    from bot.hooks import _reset
    _reset()
    yield
    _reset()
```

Place this right after the imports, before the test functions.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest tests/test_hooks.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add bot/hooks.py tests/test_hooks.py
git commit -m "feat: add bot/hooks.py — generic agent lifecycle hook registry"
```

---

### Task 2: Refactor `client.py` to use hooks instead of pixeltown imports

**Files:**
- Modify: `bot/client.py:325-346`
- Test: `tests/test_client.py` (existing — verify no regression)

- [ ] **Step 1: Replace pixeltown imports in `client.py`**

In `bot/client.py`, find and replace the block at lines 325-331:

```python
        # Notify PixelTown status tracker
        try:
            from bot.gateway.pixeltown import get_tracker
            _pt = get_tracker()
            _pt.on_working(agent.name, f"Replying in #{getattr(message.channel, 'name', 'DM')}")
        except Exception:
            pass
```

Replace with:

```python
        from bot import hooks
        hooks.fire_working(agent.name, f"Replying in #{getattr(message.channel, 'name', 'DM')}")
```

- [ ] **Step 2: Replace the finally block**

In `bot/client.py`, find and replace the block at lines 341-346:

```python
            finally:
                try:
                    from bot.gateway.pixeltown import get_tracker
                    get_tracker().on_idle(agent.name)
                except Exception:
                    pass
```

Replace with:

```python
            finally:
                hooks.fire_idle(agent.name)
```

- [ ] **Step 3: Run existing client tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest tests/test_client.py -v`
Expected: All existing tests PASS (no pixeltown dependency in test config).

- [ ] **Step 4: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add bot/client.py
git commit -m "refactor: client.py uses hooks instead of hardcoded pixeltown imports"
```

---

### Task 3: Add `ApiConfig` to config schema, replace `PixelTownConfig`

**Files:**
- Modify: `bot/config_schema.py:253-292`
- Modify: `config.yaml:63-69`
- Modify: `tests/conftest.py:68-92` (add api gateway config to test fixture)

- [ ] **Step 1: Replace `PixelTownConfig` with `ApiConfig` in `config_schema.py`**

In `bot/config_schema.py`, replace the `PixelTownConfig` class (lines 253-271):

```python
@dataclass
class PixelTownConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765
    static_dir: str = "pixeltown/pixeltown/dist"
    layout_file: str = "workspace/town_layout.json"
    sleep_after: str = "23:00"

    @classmethod
    def from_dict(cls, d: dict) -> PixelTownConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            host=_str(d.get("host"), "127.0.0.1"),
            port=_int(d.get("port"), 8765),
            static_dir=_str(d.get("static_dir"), "pixeltown/pixeltown/dist"),
            layout_file=_str(d.get("layout_file"), "workspace/town_layout.json"),
            sleep_after=_str(d.get("sleep_after"), "23:00"),
        )
```

With:

```python
@dataclass
class ApiConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8766
    api_key: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> ApiConfig:
        return cls(
            enabled=_bool(d.get("enabled"), False),
            host=_str(d.get("host"), "127.0.0.1"),
            port=_int(d.get("port"), 8766),
            api_key=_str(d.get("api_key"), ""),
        )
```

- [ ] **Step 2: Update `GatewayConfig` to use `ApiConfig`**

In `bot/config_schema.py`, replace the `GatewayConfig` class (lines 274-292):

Change `pixeltown: PixelTownConfig = field(default_factory=PixelTownConfig)` to `api: ApiConfig = field(default_factory=ApiConfig)`.

Change `pixeltown=PixelTownConfig.from_dict(d.get("pixeltown") or {})` to `api=ApiConfig.from_dict(d.get("api") or {})`.

Full replacement for `GatewayConfig`:

```python
@dataclass
class GatewayConfig:
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    imessage: IMessageConfig = field(default_factory=IMessageConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
    api: ApiConfig = field(default_factory=ApiConfig)

    @classmethod
    def from_dict(cls, d: dict) -> GatewayConfig:
        return cls(
            voice=VoiceConfig.from_dict(d.get("voice") or {}),
            volcengine=VolcengineConfig.from_dict(d.get("volcengine") or {}),
            sms=SMSConfig.from_dict(d.get("sms") or {}),
            imessage=IMessageConfig.from_dict(d.get("imessage") or {}),
            heartbeat=HeartbeatConfig.from_dict(d.get("heartbeat") or {}),
            api=ApiConfig.from_dict(d.get("api") or {}),
        )
```

- [ ] **Step 3: Update `config.yaml`**

Replace the `pixeltown` section (lines 63-69):

```yaml
  pixeltown:
    enabled: true
    host: "127.0.0.1"
    port: 8765
    static_dir: "pixeltown/pixeltown/dist"
    layout_file: "workspace/town_layout.json"
    sleep_after: "23:00"
```

With:

```yaml
  api:
    enabled: false
    host: "127.0.0.1"
    port: 8766
    api_key: ""
```

- [ ] **Step 4: Update test fixture in `conftest.py`**

In `tests/conftest.py`, add the `api` gateway config to the test config dict. After the `"heartbeat": {"enabled": False},` line (line 91), add:

```python
            "api": {"enabled": False},
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add bot/config_schema.py config.yaml tests/conftest.py
git commit -m "refactor: replace PixelTownConfig with ApiConfig in config schema"
```

---

### Task 4: Create `bot/gateway/api.py` — HTTP/WS API gateway

**Files:**
- Create: `bot/gateway/api.py`
- Test: `tests/gateway/test_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/gateway/test_api.py`:

```python
"""Tests for bot.gateway.api — HTTP/WS API gateway."""

import asyncio
import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from bot.gateway.api import create_api_app, _ws_clients


@pytest.fixture
def _clean_ws():
    """Clear WS client set between tests."""
    _ws_clients.clear()
    yield
    _ws_clients.clear()


@pytest.fixture
async def api_client(_clean_ws):
    """Create a test client for the API app."""
    app = create_api_app(api_key="")
    async with TestClient(TestServer(app)) as client:
        yield client


@pytest.fixture
async def api_client_with_key(_clean_ws):
    """Create a test client for the API app with API key auth."""
    app = create_api_app(api_key="test-secret")
    async with TestClient(TestServer(app)) as client:
        yield client


@pytest.mark.asyncio
async def test_get_agents(api_client):
    """GET /api/agents returns agent list."""
    from bot.status import AgentStatusTracker
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
    with patch("bot.gateway.api.llm") as mock_llm:
        mock_llm.reply = AsyncMock(return_value="Hello back!")
        resp = await api_client.post(
            "/api/chat",
            json={"session_key": "pixeltown:agent1", "text": "hello"},
        )
        assert resp.status == 200
        data = await resp.json()
        assert data["ok"] is True
        assert data["reply"] == "Hello back!"
        mock_llm.reply.assert_called_once()


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest tests/gateway/test_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'bot.gateway.api'`

- [ ] **Step 3: Write the implementation**

Create `bot/gateway/api.py`:

```python
"""HTTP/WS API gateway — exposes miniclaw capabilities to external consumers.

Endpoints:
  POST /api/chat           Send message to LLM, get reply
  GET  /api/agents         List agents and their status
  GET  /ws/events          WebSocket stream of agent status events
"""

import asyncio
import json
import logging

from aiohttp import web

from bot import hooks
from bot.config import get_config
from bot.logger import get_logger
from bot.message import build_user_content
from bot.status import AgentStatusTracker, AgentState

log = get_logger("api")

_tracker: AgentStatusTracker | None = None
_ws_clients: set[web.WebSocketResponse] = set()
_api_key: str = ""


# ── Middleware ───────────────────────────────────────────────────────────────

@web.middleware
async def auth_middleware(request: web.Request, handler):
    """Check X-API-Key header if api_key is configured."""
    if _api_key and request.path.startswith(("/api/", "/ws/")):
        key = request.headers.get("X-API-Key", "")
        if key != _api_key:
            return web.json_response({"error": "unauthorized"}, status=401)
    return await handler(request)


# ── REST Handlers ───────────────────────────────────────────────────────────

async def _handle_agents(request: web.Request) -> web.Response:
    """GET /api/agents — list all agents and their status."""
    statuses = _tracker.get_all_statuses() if _tracker else {}
    agents = [{"id": aid, **info} for aid, info in statuses.items()]
    return web.json_response(agents)


async def _handle_chat(request: web.Request) -> web.Response:
    """POST /api/chat — send message to LLM, return reply."""
    data = await request.json()
    session_key = data.get("session_key", "")
    text = data.get("text", "")
    if not session_key or not text:
        return web.json_response(
            {"error": "session_key and text are required"}, status=400
        )

    from bot import llm

    try:
        user_content = build_user_content(text)
        reply = await llm.reply(session_key, user_content)
        return web.json_response({"ok": True, "reply": reply})
    except Exception as e:
        log.exception("chat error for session %s", session_key)
        return web.json_response({"ok": False, "error": str(e)}, status=500)


# ── WebSocket Handler ───────────────────────────────────────────────────────

async def _handle_ws_events(request: web.Request) -> web.WebSocketResponse:
    """GET /ws/events — stream agent status changes to client."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    _ws_clients.add(ws)
    log.info("API WS client connected (%d total)", len(_ws_clients))

    try:
        async for msg in ws:
            pass  # We only push, clients don't send
    finally:
        _ws_clients.discard(ws)
        log.info("API WS client disconnected (%d remaining)", len(_ws_clients))

    return ws


async def _broadcast(msg: dict) -> None:
    """Push a JSON message to all connected WS clients."""
    for ws in list(_ws_clients):
        if not ws.closed:
            try:
                await ws.send_json(msg)
            except Exception:
                _ws_clients.discard(ws)


def _on_agent_working(agent_id: str, detail: str) -> None:
    """Hook callback: agent started working."""
    asyncio.create_task(_broadcast({
        "type": "agent_working",
        "agent": agent_id,
        "detail": detail,
    }))


def _on_agent_idle(agent_id: str) -> None:
    """Hook callback: agent became idle."""
    asyncio.create_task(_broadcast({
        "type": "agent_idle",
        "agent": agent_id,
    }))


# ── App Factory ─────────────────────────────────────────────────────────────

def create_api_app(api_key: str = "") -> web.Application:
    """Create the aiohttp Application (useful for testing)."""
    global _api_key
    _api_key = api_key

    app = web.Application(middlewares=[auth_middleware])
    app.router.add_get("/api/agents", _handle_agents)
    app.router.add_post("/api/chat", _handle_chat)
    app.router.add_get("/ws/events", _handle_ws_events)
    return app


# ── Lifecycle ───────────────────────────────────────────────────────────────

def get_tracker() -> AgentStatusTracker:
    """Get or create the global status tracker."""
    global _tracker
    if _tracker is None:
        _tracker = AgentStatusTracker([])
    return _tracker


async def start_api_server() -> None:
    """Start the API gateway. Runs until cancelled."""
    cfg = get_config().gateway.api

    global _tracker
    _tracker = get_tracker()

    # Register hooks so status changes are pushed to WS clients
    hooks.register_on_working(_on_agent_working)
    hooks.register_on_idle(_on_agent_idle)

    app = create_api_app(api_key=cfg.api_key)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.host, cfg.port)
    await site.start()
    log.info("API gateway at http://%s:%d", cfg.host, cfg.port)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest tests/gateway/test_api.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add bot/gateway/api.py tests/gateway/test_api.py
git commit -m "feat: add bot/gateway/api.py — HTTP/WS API gateway for external consumers"
```

---

### Task 5: Update `main.py` — replace pixeltown with API gateway

**Files:**
- Modify: `main.py:71-81`

- [ ] **Step 1: Replace pixeltown startup block**

In `main.py`, replace lines 71-80:

```python
        _gw_cfg = get_config().gateway

        if _gw_cfg.pixeltown.enabled:
            from bot.gateway.pixeltown import start_pixeltown_server, get_tracker
            # Register only Discord-connected agents with the status tracker
            tracker = get_tracker()
            for agent in agents:
                if agent.discord_token:
                    tracker.on_online(agent.name)
            tasks.append(start_pixeltown_server())
```

With:

```python
        _gw_cfg = get_config().gateway

        if _gw_cfg.api.enabled:
            from bot.gateway.api import start_api_server, get_tracker
            tracker = get_tracker()
            for agent in agents:
                if agent.discord_token:
                    tracker.on_online(agent.name)
            tasks.append(start_api_server())
```

- [ ] **Step 2: Run all tests to verify no regression**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add main.py
git commit -m "refactor: main.py uses API gateway instead of pixeltown gateway"
```

---

### Task 6: Delete `bot/gateway/pixeltown.py`

**Files:**
- Delete: `bot/gateway/pixeltown.py`

- [ ] **Step 1: Verify no remaining imports**

Run: `cd /Users/sen/side_project/miniclaw && grep -r "bot.gateway.pixeltown\|from bot.gateway.pixeltown\|gateway.pixeltown" bot/ main.py tests/ --include="*.py"`
Expected: No matches (all references already removed in Tasks 2 and 5).

- [ ] **Step 2: Delete the file**

```bash
rm /Users/sen/side_project/miniclaw/bot/gateway/pixeltown.py
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add -u bot/gateway/pixeltown.py
git commit -m "chore: remove bot/gateway/pixeltown.py — moved to standalone project"
```

---

### Task 7: Create standalone pixeltown project — structure and config

**Files:**
- Create: `/Users/sen/side_project/pixeltown/pyproject.toml`
- Create: `/Users/sen/side_project/pixeltown/config.yaml`
- Create: `/Users/sen/side_project/pixeltown/server/__init__.py`
- Create: `/Users/sen/side_project/pixeltown/server/main.py`

- [ ] **Step 1: Create project directory**

```bash
mkdir -p /Users/sen/side_project/pixeltown/server
mkdir -p /Users/sen/side_project/pixeltown/tests
```

- [ ] **Step 2: Create `pyproject.toml`**

Create `/Users/sen/side_project/pixeltown/pyproject.toml`:

```toml
[project]
name = "pixeltown"
version = "0.1.0"
description = "PixelTown — pixel-art agent visualization frontend"
requires-python = ">=3.13"
dependencies = [
    "aiohttp>=3.9",
    "pyyaml>=6.0",
]

[project.optional-dependencies]
dev = ["pytest", "pytest-asyncio"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create `config.yaml`**

Create `/Users/sen/side_project/pixeltown/config.yaml`:

```yaml
miniclaw:
  api_url: "http://127.0.0.1:8766"
  api_key: ""

server:
  host: "127.0.0.1"
  port: 8765
  static_dir: "frontend/dist"

town:
  layout_file: "data/town_layout.json"
  sleep_after: "23:00"
```

- [ ] **Step 4: Create `server/__init__.py`**

Create `/Users/sen/side_project/pixeltown/server/__init__.py`:

```python
"""PixelTown server — standalone backend for the pixel-art visualization UI."""
```

- [ ] **Step 5: Create entry point `server/main.py`**

Create `/Users/sen/side_project/pixeltown/server/main.py`:

```python
"""PixelTown server entry point."""

import asyncio
import logging
import sys
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
log = logging.getLogger("pixeltown")


def load_config(path: str = "config.yaml") -> dict:
    """Load config.yaml and return as dict."""
    p = Path(path)
    if not p.exists():
        log.warning("Config %s not found, using defaults", path)
        return {}
    return yaml.safe_load(p.read_text()) or {}


async def main():
    cfg = load_config()
    miniclaw_cfg = cfg.get("miniclaw", {})
    server_cfg = cfg.get("server", {})

    from server.miniclaw_client import MiniclawClient
    from server.gateway import PixelTownServer

    client = MiniclawClient(
        api_url=miniclaw_cfg.get("api_url", "http://127.0.0.1:8766"),
        api_key=miniclaw_cfg.get("api_key", ""),
    )

    server = PixelTownServer(
        miniclaw=client,
        host=server_cfg.get("host", "127.0.0.1"),
        port=server_cfg.get("port", 8765),
        static_dir=server_cfg.get("static_dir", "frontend/dist"),
        layout_file=cfg.get("town", {}).get("layout_file", "data/town_layout.json"),
    )

    await asyncio.gather(
        client.subscribe_events(),
        server.start(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
```

- [ ] **Step 6: Commit**

```bash
cd /Users/sen/side_project/pixeltown
git init
git add pyproject.toml config.yaml server/__init__.py server/main.py
git commit -m "init: pixeltown standalone project — config and entry point"
```

---

### Task 8: Create `server/miniclaw_client.py` — HTTP/WS client to miniclaw

**Files:**
- Create: `/Users/sen/side_project/pixeltown/server/miniclaw_client.py`
- Test: `/Users/sen/side_project/pixeltown/tests/test_miniclaw_client.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/sen/side_project/pixeltown/tests/test_miniclaw_client.py`:

```python
"""Tests for MiniclawClient — HTTP/WS client to miniclaw API."""

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from server.miniclaw_client import MiniclawClient


@pytest.fixture
def client():
    return MiniclawClient(api_url="http://localhost:8766", api_key="test-key")


@pytest.mark.asyncio
async def test_chat_sends_post_and_returns_reply(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value={"ok": True, "reply": "Hi!"})

    mock_session = AsyncMock()
    mock_session.post = AsyncMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        reply = await client.chat("pixeltown:agent1", "hello")

    assert reply == "Hi!"
    mock_session.post.assert_called_once()
    call_kwargs = mock_session.post.call_args
    assert "X-API-Key" in call_kwargs[1].get("headers", {}) or \
           "X-API-Key" in call_kwargs.kwargs.get("headers", {})


@pytest.mark.asyncio
async def test_chat_returns_error_on_failure(client):
    mock_resp = AsyncMock()
    mock_resp.status = 500
    mock_resp.json = AsyncMock(return_value={"ok": False, "error": "boom"})

    mock_session = AsyncMock()
    mock_session.post = AsyncMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        reply = await client.chat("key", "text")

    assert reply is None


@pytest.mark.asyncio
async def test_get_agents(client):
    mock_resp = AsyncMock()
    mock_resp.status = 200
    mock_resp.json = AsyncMock(return_value=[{"id": "bot1", "status": "idle"}])

    mock_session = AsyncMock()
    mock_session.get = AsyncMock(return_value=mock_resp)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)

    with patch("aiohttp.ClientSession", return_value=mock_session):
        agents = await client.get_agents()

    assert len(agents) == 1
    assert agents[0]["id"] == "bot1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sen/side_project/pixeltown && python -m pytest tests/test_miniclaw_client.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `/Users/sen/side_project/pixeltown/server/miniclaw_client.py`:

```python
"""HTTP/WS client to miniclaw's API gateway.

Handles all communication with the miniclaw bot process:
- POST /api/chat for LLM interaction
- GET /api/agents for status queries
- WS /ws/events for real-time status updates
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Callable

import aiohttp

log = logging.getLogger("pixeltown.client")


class MiniclawClient:
    """Client for miniclaw's HTTP/WS API."""

    def __init__(self, api_url: str, api_key: str = "") -> None:
        self._api_url = api_url.rstrip("/")
        self._api_key = api_key
        self._listeners: list[Callable[[dict], None]] = []

    def _headers(self) -> dict[str, str]:
        h: dict[str, str] = {}
        if self._api_key:
            h["X-API-Key"] = self._api_key
        return h

    async def chat(self, session_key: str, text: str) -> str | None:
        """Send a message to miniclaw LLM, return the reply text."""
        url = f"{self._api_url}/api/chat"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"session_key": session_key, "text": text},
                    headers=self._headers(),
                ) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("ok"):
                        return data["reply"]
                    log.warning("chat error: %s", data)
                    return None
        except Exception:
            log.exception("Failed to reach miniclaw at %s", url)
            return None

    async def get_agents(self) -> list[dict]:
        """Fetch all agents and their status from miniclaw."""
        url = f"{self._api_url}/api/agents"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self._headers()) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    log.warning("get_agents error: %d", resp.status)
                    return []
        except Exception:
            log.exception("Failed to reach miniclaw at %s", url)
            return []

    def add_event_listener(self, cb: Callable[[dict], None]) -> None:
        """Register callback for real-time events from miniclaw."""
        self._listeners.append(cb)

    async def subscribe_events(self) -> None:
        """Connect to miniclaw WS /ws/events and dispatch to listeners.

        Auto-reconnects on disconnect with exponential backoff.
        """
        url = f"{self._api_url.replace('http', 'ws')}/ws/events"
        backoff = 1
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(
                        url, headers=self._headers()
                    ) as ws:
                        log.info("Connected to miniclaw events at %s", url)
                        backoff = 1
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                data = json.loads(msg.data)
                                for cb in self._listeners:
                                    try:
                                        cb(data)
                                    except Exception:
                                        log.exception("Event listener error")
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
            except Exception:
                log.warning(
                    "miniclaw WS disconnected, reconnecting in %ds...", backoff
                )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/sen/side_project/pixeltown && python -m pytest tests/test_miniclaw_client.py -v`
Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/sen/side_project/pixeltown
git add server/miniclaw_client.py tests/test_miniclaw_client.py
git commit -m "feat: add MiniclawClient — HTTP/WS client for miniclaw API"
```

---

### Task 9: Create `server/gateway.py` — browser-facing server

**Files:**
- Create: `/Users/sen/side_project/pixeltown/server/gateway.py`
- Test: `/Users/sen/side_project/pixeltown/tests/test_gateway.py`

- [ ] **Step 1: Write failing tests**

Create `/Users/sen/side_project/pixeltown/tests/test_gateway.py`:

```python
"""Tests for PixelTownServer — browser-facing WS + static server."""

import json
import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from server.gateway import PixelTownServer


@pytest.fixture
def miniclaw():
    client = MagicMock()
    client.chat = AsyncMock(return_value="LLM says hi")
    client.get_agents = AsyncMock(return_value=[{"id": "bot1", "status": "idle"}])
    client.add_event_listener = MagicMock()
    return client


@pytest.fixture
def server(miniclaw, tmp_path):
    return PixelTownServer(
        miniclaw=miniclaw,
        host="127.0.0.1",
        port=8765,
        static_dir=str(tmp_path / "dist"),
        layout_file=str(tmp_path / "layout.json"),
    )


def test_load_layout_empty(server):
    assert server._load_layout() == []


def test_save_and_load_layout(server):
    buildings = [{"id": "cottage-1", "x": 3, "y": 3}]
    server._save_layout(buildings)
    assert server._load_layout() == buildings


def test_current_season():
    season = PixelTownServer._current_season()
    assert season in ("spring", "summer", "autumn", "winter")


def test_on_miniclaw_event_updates_local_status(server):
    server._on_miniclaw_event({
        "type": "agent_working",
        "agent": "bot1",
        "detail": "busy",
    })
    assert server._agent_statuses["bot1"]["status"] == "working"


def test_on_miniclaw_event_idle(server):
    server._on_miniclaw_event({
        "type": "agent_idle",
        "agent": "bot1",
    })
    assert server._agent_statuses["bot1"]["status"] == "idle"


@pytest.mark.asyncio
async def test_process_message_calls_miniclaw(server, miniclaw):
    reply = await server._process_message("bot1", "hello")
    assert reply == "LLM says hi"
    miniclaw.chat.assert_called_once_with("pixeltown:bot1", "hello")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/sen/side_project/pixeltown && python -m pytest tests/test_gateway.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `/Users/sen/side_project/pixeltown/server/gateway.py`:

```python
"""PixelTown browser-facing server — aiohttp WS + static files.

Receives status updates from MiniclawClient and pushes them to browser
clients. Routes user messages from the browser to miniclaw via HTTP.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from pathlib import Path

from aiohttp import web

log = logging.getLogger("pixeltown.gateway")


class PixelTownServer:
    """aiohttp server: serves frontend, WS to browsers, bridges to miniclaw."""

    def __init__(
        self,
        miniclaw,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        static_dir: str = "frontend/dist",
        layout_file: str = "data/town_layout.json",
    ) -> None:
        self._miniclaw = miniclaw
        self._host = host
        self._port = port
        self._static_dir = Path(static_dir)
        self._layout_file = Path(layout_file)
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._agent_statuses: dict[str, dict] = {}

        # Subscribe to miniclaw events
        miniclaw.add_event_listener(self._on_miniclaw_event)

    # ── Miniclaw event handler ──

    def _on_miniclaw_event(self, event: dict) -> None:
        """Handle a status event pushed from miniclaw."""
        event_type = event.get("type", "")
        agent_id = event.get("agent", "")

        if event_type == "agent_working":
            self._agent_statuses[agent_id] = {
                "status": "working",
                "detail": event.get("detail", ""),
            }
        elif event_type == "agent_idle":
            self._agent_statuses[agent_id] = {"status": "idle", "detail": ""}
        elif event_type == "agent_online":
            self._agent_statuses.setdefault(agent_id, {"status": "idle", "detail": ""})

        # Forward to browser clients
        for ws in list(self._ws_clients):
            if not ws.closed:
                asyncio.create_task(ws.send_json({
                    "type": "agent_status",
                    "agent": agent_id,
                    "status": self._agent_statuses.get(agent_id, {}).get("status", "offline"),
                    "detail": self._agent_statuses.get(agent_id, {}).get("detail", ""),
                }))

    # ── WebSocket (browser) ──

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        log.info("Browser connected (%d total)", len(self._ws_clients))

        # Send initial state
        await ws.send_json({
            "type": "init",
            "agents": [
                {"id": aid, **info}
                for aid, info in self._agent_statuses.items()
            ],
            "season": self._current_season(),
            "town_layout": self._load_layout(),
        })

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_browser_message(ws, json.loads(msg.data))
        finally:
            self._ws_clients.discard(ws)
            log.info("Browser disconnected (%d remaining)", len(self._ws_clients))

        return ws

    async def _handle_browser_message(
        self, ws: web.WebSocketResponse, data: dict
    ) -> None:
        msg_type = data.get("type")

        if msg_type == "save_layout":
            self._save_layout(data.get("buildings", []))

        elif msg_type == "send_message":
            agent_id = data.get("agent", "")
            text = data.get("text", "")
            log.info("Browser → %s: %s", agent_id, text[:80])
            reply = await self._process_message(agent_id, text)
            await ws.send_json({
                "type": "message_received",
                "agent": agent_id,
                "reply": reply or "",
            })

    async def _process_message(self, agent_id: str, text: str) -> str | None:
        """Route message to miniclaw LLM via HTTP."""
        session_key = f"pixeltown:{agent_id}"
        return await self._miniclaw.chat(session_key, text)

    # ── Helpers ──

    def _load_layout(self) -> list[dict]:
        if self._layout_file.exists():
            return json.loads(self._layout_file.read_text())
        return []

    def _save_layout(self, buildings: list[dict]) -> None:
        self._layout_file.parent.mkdir(parents=True, exist_ok=True)
        self._layout_file.write_text(json.dumps(buildings, indent=2))

    @staticmethod
    def _current_season() -> str:
        month = datetime.datetime.now().month
        if 3 <= month <= 5:
            return "spring"
        if 6 <= month <= 8:
            return "summer"
        if 9 <= month <= 11:
            return "autumn"
        return "winter"

    # ── Lifecycle ──

    async def start(self) -> None:
        """Start the aiohttp server. Runs until cancelled."""
        app = web.Application()
        app.router.add_get("/ws", self._ws_handler)

        if self._static_dir.exists():
            app.router.add_static("/", self._static_dir, name="static")
        else:
            log.warning("Static dir %s not found", self._static_dir)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()
        log.info("PixelTown at http://%s:%d", self._host, self._port)

        try:
            await asyncio.Event().wait()
        finally:
            await runner.cleanup()
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/sen/side_project/pixeltown && python -m pytest tests/test_gateway.py -v`
Expected: All 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/sen/side_project/pixeltown
git add server/gateway.py tests/test_gateway.py
git commit -m "feat: add PixelTownServer — browser-facing WS + static server"
```

---

### Task 10: Move frontend and assets from miniclaw to pixeltown

**Files:**
- Move: `miniclaw/pixeltown/pixeltown/` → `pixeltown/frontend/`
- Move: `miniclaw/pixeltown/docs/` → `pixeltown/docs/`
- Move: `miniclaw/pixeltown/scripts/` → `pixeltown/scripts/`
- Move: `miniclaw/pixeltown/README.md` → `pixeltown/README.md`

- [ ] **Step 1: Move frontend directory**

```bash
cp -r /Users/sen/side_project/miniclaw/pixeltown/pixeltown/ /Users/sen/side_project/pixeltown/frontend/
```

- [ ] **Step 2: Move docs, scripts, README**

```bash
cp -r /Users/sen/side_project/miniclaw/pixeltown/docs/ /Users/sen/side_project/pixeltown/docs/
cp -r /Users/sen/side_project/miniclaw/pixeltown/scripts/ /Users/sen/side_project/pixeltown/scripts/
cp /Users/sen/side_project/miniclaw/pixeltown/README.md /Users/sen/side_project/pixeltown/README.md
```

- [ ] **Step 3: Create `.gitignore`**

Create `/Users/sen/side_project/pixeltown/.gitignore`:

```
node_modules/
frontend/dist/
frontend/node_modules/
__pycache__/
*.pyc
.venv/
data/
```

- [ ] **Step 4: Verify frontend builds**

```bash
cd /Users/sen/side_project/pixeltown/frontend && npm install && npm run build
```

Expected: Build succeeds, `frontend/dist/` is created.

- [ ] **Step 5: Commit in pixeltown repo**

```bash
cd /Users/sen/side_project/pixeltown
git add .gitignore README.md frontend/ docs/ scripts/
git commit -m "feat: move frontend, docs, and scripts from miniclaw"
```

---

### Task 11: Remove `pixeltown/` directory from miniclaw

**Files:**
- Delete: `miniclaw/pixeltown/` (entire directory)

- [ ] **Step 1: Verify no remaining references in miniclaw code**

```bash
cd /Users/sen/side_project/miniclaw && grep -r "pixeltown/pixeltown\|pixeltown/dist\|pixeltown/src" bot/ main.py tests/ config.yaml --include="*.py" --include="*.yaml"
```

Expected: No matches.

- [ ] **Step 2: Delete the pixeltown directory from miniclaw**

```bash
rm -rf /Users/sen/side_project/miniclaw/pixeltown/
```

- [ ] **Step 3: Run all miniclaw tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit in miniclaw repo**

```bash
cd /Users/sen/side_project/miniclaw
git add -A
git commit -m "chore: remove pixeltown/ directory — now a standalone project"
```

---

### Task 12: Update CLAUDE.md — remove pixeltown references, add API gateway docs

**Files:**
- Modify: `/Users/sen/side_project/miniclaw/CLAUDE.md`

- [ ] **Step 1: Update project structure**

In CLAUDE.md, remove `pixeltown/` from the project structure tree. Add `bot/hooks.py` and `bot/gateway/api.py` to the tree:

Under `bot/`:
```
│   ├── hooks.py                     # Agent lifecycle hook registry
```

Under `bot/gateway/`:
```
│   ├── gateway/                     # Non-Discord inbound/outbound gateways
│   │   ├── __init__.py
│   │   ├── api.py                   # HTTP/WS API gateway for external consumers
│   │   ├── voice.py                 # Voice: mic → STT → wake → LLM → TTS → speaker
```

- [ ] **Step 2: Update config.yaml documentation**

Replace the pixeltown gateway references in the config docs with the API gateway. In the `config.yaml sections` table, change the `gateway` entry to include `api` settings instead of pixeltown.

- [ ] **Step 3: Update Architecture Overview**

Remove pixeltown-specific references from the architecture diagram. Add a note about the API gateway.

- [ ] **Step 4: Commit**

```bash
cd /Users/sen/side_project/miniclaw
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md — replace pixeltown with API gateway docs"
```
