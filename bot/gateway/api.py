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
from bot.gateway.status import AgentStatusTracker, AgentState

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
