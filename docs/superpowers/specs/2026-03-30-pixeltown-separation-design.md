# PixelTown Separation: Design Spec

**Date:** 2026-03-30
**Status:** Approved

## Goal

Separate PixelTown from the miniclaw monorepo into a fully independent project. The two communicate exclusively over HTTP/WebSocket — zero Python import dependency between them.

## Architecture

```
miniclaw (Discord bot process)           pixeltown (standalone process)
┌────────────────────────────┐           ┌────────────────────────────┐
│                            │           │                            │
│  bot/gateway/api.py        │           │  server.py                 │
│  ┌──────────────────────┐  │           │  ┌──────────────────────┐  │
│  │ POST /api/chat       │◄─┼───HTTP────┼──│ user sends message   │  │
│  │  → llm.reply()       │──┼───JSON───►┼──│ → forward to browser │  │
│  │  → return reply      │  │           │  │                      │  │
│  │                      │  │           │  │                      │  │
│  │ WS /ws/events        │──┼───push───►┼──│ → forward status     │  │
│  │  agent_working       │  │           │  │   to browser clients │  │
│  │  agent_idle          │  │           │  │                      │  │
│  └──────────────────────┘  │           │  │ WS /ws (browser)     │  │
│                            │           │  │ Static file serving   │  │
│  bot/hooks.py              │           │  └──────────────────────┘  │
│  ┌──────────────────────┐  │           │                            │
│  │ fire_working() ──────┼──┼──► api.py │  No miniclaw dependency   │
│  │ fire_idle()   ──────┼──┼──► pushes  │  Only needs: aiohttp      │
│  └──────────────────────┘  │  to WS    │                            │
│                            │           └────────────────────────────┘
│  bot/status.py (unchanged) │
│  client.py → hooks.fire()  │
└────────────────────────────┘
```

## Part 1: miniclaw Changes

### 1.1 New: `bot/hooks.py` — Agent lifecycle hooks

Lightweight callback registry replacing hardcoded pixeltown imports in `client.py`.

```python
# bot/hooks.py
from __future__ import annotations
from typing import Callable

_on_working: list[Callable[[str, str], None]] = []   # (agent_id, detail)
_on_idle: list[Callable[[str], None]] = []            # (agent_id)

def register_on_working(cb: Callable[[str, str], None]) -> None:
    _on_working.append(cb)

def register_on_idle(cb: Callable[[str], None]) -> None:
    _on_idle.append(cb)

def fire_working(agent_id: str, detail: str = "") -> None:
    for cb in _on_working:
        try:
            cb(agent_id, detail)
        except Exception:
            pass

def fire_idle(agent_id: str) -> None:
    for cb in _on_idle:
        try:
            cb(agent_id)
        except Exception:
            pass
```

### 1.2 New: `bot/gateway/api.py` — External HTTP/WS API

aiohttp server exposing miniclaw capabilities to external consumers.

**Endpoints:**

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` | Send message to LLM, get reply |
| `GET` | `/ws/events` | WebSocket stream of agent status events |
| `GET` | `/api/agents` | List all agents and their current status |

**POST /api/chat:**
```json
// Request
{"session_key": "pixeltown:agent1", "text": "hello"}

// Response
{"ok": true, "reply": "Hi there!"}
```

**WS /ws/events push messages:**
```json
{"type": "agent_working", "agent": "miniclaw", "detail": "Replying in #general"}
{"type": "agent_idle", "agent": "miniclaw"}
{"type": "agent_online", "agent": "miniclaw"}
```

**Config:**
```yaml
gateway:
  api:
    enabled: false          # default off
    host: "127.0.0.1"
    port: 8766
    api_key: ""             # optional simple auth (checked via X-API-Key header)
```

**Implementation:** On startup, registers hooks via `bot.hooks` to capture status changes and push them to connected WS clients. Chat endpoint calls `llm.reply()` and returns the result.

### 1.3 Modify: `bot/client.py`

Replace hardcoded pixeltown imports (lines 325-346):

```python
# Before
from bot.gateway.pixeltown import get_tracker
_pt = get_tracker()
_pt.on_working(agent.name, ...)

# After
from bot import hooks
hooks.fire_working(agent.name, f"Replying in #{channel_name}")
# ... and in finally:
hooks.fire_idle(agent.name)
```

### 1.4 Modify: `main.py`

- Remove pixeltown gateway startup block (lines 73-80)
- Add API gateway startup:

```python
if _gw_cfg.api.enabled:
    from bot.gateway.api import start_api_server
    tasks.append(start_api_server())
```

### 1.5 Modify: `config.yaml`

- Remove `gateway.pixeltown` section
- Add `gateway.api` section (enabled: false by default)

### 1.6 Modify: `bot/config_schema.py`

- Remove `PixelTownConfig` dataclass
- Add `ApiConfig` dataclass
- Update `GatewayConfig` to replace `pixeltown` field with `api`

### 1.7 Keep unchanged

- `bot/status.py` — generic, stays in miniclaw
- `bot/utils/session_keys.py` — `pixeltown_key()` can stay (it's a trivial string helper, any gateway can use it)

### 1.8 Delete

- `bot/gateway/pixeltown.py` — moved to standalone project

## Part 2: Standalone PixelTown Project

### 2.1 Location

`/Users/sen/side_project/pixeltown/` — new git repo.

### 2.2 Structure

```
pixeltown/
├── pyproject.toml              # Python package metadata
├── README.md
├── config.yaml                 # pixeltown's own config
│
├── server/                     # Python backend
│   ├── __init__.py
│   ├── main.py                 # Entry point
│   ├── gateway.py              # aiohttp: WS to browsers + static files
│   ├── miniclaw_client.py      # HTTP/WS client to miniclaw API
│   └── status.py               # Local status cache (receives from miniclaw WS)
│
├── frontend/                   # Vite + PixiJS (moved from pixeltown/pixeltown/)
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── index.html
│   ├── src/                    # All existing TS source
│   ├── editor/                 # Sprite/map editor
│   └── public/                 # Assets (sprites, tiles, maps)
│
├── docs/
│   └── pixeltown-design.md     # Moved from pixeltown/docs/
│
├── scripts/
│   └── gen_sprites.py
│
└── tests/
    ├── test_gateway.py
    └── test_miniclaw_client.py
```

### 2.3 `server/miniclaw_client.py`

Handles all communication with miniclaw:

```python
class MiniclawClient:
    def __init__(self, api_url: str, api_key: str = ""):
        self._api_url = api_url   # e.g. "http://127.0.0.1:8766"
        self._api_key = api_key

    async def chat(self, session_key: str, text: str) -> str:
        """POST /api/chat → get LLM reply."""

    async def subscribe_events(self, callback):
        """Connect to WS /ws/events, call callback on each event."""

    async def get_agents(self) -> list[dict]:
        """GET /api/agents → agent list."""
```

### 2.4 `server/gateway.py`

The browser-facing server (adapted from current `bot/gateway/pixeltown.py`):
- Serves frontend static files
- WS endpoint for browser clients
- Receives status updates from `MiniclawClient` and pushes to browsers
- Receives user messages from browsers, forwards to miniclaw via `MiniclawClient.chat()`

### 2.5 Config

```yaml
# pixeltown/config.yaml
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

### 2.6 Dependencies

```toml
# pyproject.toml
[project]
name = "pixeltown"
dependencies = ["aiohttp", "pyyaml"]
# No miniclaw dependency
```

### 2.7 What to discard

- `pixeltown/src/status.py` — duplicate, not needed
- `pixeltown/src/gateway_pixeltown.py` — duplicate, replaced by `server/gateway.py`
- `pixeltown/.ralphrc` — project-specific tooling, discard unless still needed

## Part 3: What NOT to change

- Frontend code (all TS/PixiJS) moves as-is, no modifications
- `bot/status.py` stays in miniclaw
- Existing gateway pattern (SMS, iMessage, Voice) untouched
- No plugin auto-discovery, entry points, or framework overhead

## Migration Path

1. Create miniclaw's `bot/hooks.py` and `bot/gateway/api.py`
2. Refactor `client.py` to use hooks instead of hardcoded pixeltown imports
3. Update `config_schema.py`, `config.yaml`, `main.py`
4. Delete `bot/gateway/pixeltown.py`
5. Create standalone pixeltown project at `/Users/sen/side_project/pixeltown/`
6. Move frontend, adapt gateway to use HTTP client
7. Delete `pixeltown/` directory from miniclaw repo
8. Test both projects independently
