"""PixelTown WebSocket + REST gateway — aiohttp server.

Serves the PixelTown frontend (pixeltown/dist/) and provides a WebSocket +
REST API for real-time agent status visualization and user interaction.
"""

import asyncio
import json
import logging
from pathlib import Path

from aiohttp import web

from bot.config import get_config
from bot.logger import get_logger
from bot.message import build_user_content
from bot.status import AgentStatusTracker, AgentState
from bot.utils.session_keys import pixeltown_key

log = get_logger("pixeltown")


class PixelTownGateway:
    """aiohttp server: static files + WebSocket + REST API."""

    def __init__(
        self,
        status_tracker: AgentStatusTracker,
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        static_dir: str = "pixeltown/pixeltown/dist",
        layout_file: str = "workspace/town_layout.json",
    ) -> None:
        self._tracker = status_tracker
        self._host = host
        self._port = port
        self._static_dir = Path(static_dir)
        self._layout_file = Path(layout_file)
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._cron_jobs: list[dict] = []

        self._tracker.add_listener(self._on_status_change)

    def set_cron_jobs(self, jobs: list[dict]) -> None:
        self._cron_jobs = jobs

    # ── WebSocket ──

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)
        log.info("WS client connected (%d total)", len(self._ws_clients))

        await ws.send_json({
            "type": "init",
            "agents": self._build_agents_list(),
            "weather": {"type": "sunny", "since": 0, "next_change": 0},
            "season": self._current_season(),
            "town_layout": self._load_layout(),
            "affinity": self._tracker.get_all_affinities(),
        })

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, json.loads(msg.data))
                elif msg.type == web.WSMsgType.ERROR:
                    log.warning("WS error: %s", ws.exception())
        finally:
            self._ws_clients.discard(ws)
            log.info("WS client disconnected (%d remaining)", len(self._ws_clients))

        return ws

    async def _handle_ws_message(self, ws: web.WebSocketResponse, data: dict) -> None:
        msg_type = data.get("type")

        if msg_type == "save_layout":
            self._save_layout(data.get("buildings", []))

        elif msg_type == "send_message":
            agent_id = data.get("agent", "")
            text = data.get("text", "")
            log.info("WS send_message → %s: %s", agent_id, text[:80])
            # Route to MiniClaw LLM
            asyncio.create_task(self._process_message(agent_id, text))

        elif msg_type == "trigger_task":
            agent_id = data.get("agent", "")
            job_id = data.get("job_id", "")
            log.info("WS trigger_task → %s: %s", agent_id, job_id)
            self._tracker.on_working(agent_id, f"Running: {job_id}")
            await self._broadcast({
                "type": "cron_event",
                "agent": agent_id,
                "job": job_id,
                "action": "started",
            })

        elif msg_type == "toggle_agent":
            agent_id = data.get("agent", "")
            enabled = data.get("enabled", True)
            log.info("WS toggle_agent → %s: enabled=%s", agent_id, enabled)
            if enabled:
                self._tracker.on_online(agent_id)
            else:
                self._tracker.on_offline(agent_id)

    async def _process_message(self, agent_id: str, text: str) -> None:
        """Route a message from PixelTown UI to the MiniClaw LLM."""
        try:
            session_key = pixeltown_key(agent_id)
            user_content = build_user_content(text)

            from bot import llm
            reply_text = await llm.reply(session_key, user_content)

            # Broadcast the reply back as a message_received event
            await self._broadcast({
                "type": "message_received",
                "agent": agent_id,
                "from": "user",
                "preview": reply_text[:80] if reply_text else "",
            })
            log.info("LLM reply for %s: %s", agent_id, (reply_text or "")[:60])
        except Exception:
            log.exception("Failed to process message for %s", agent_id)

    # ── REST API ──

    async def _api_agents(self, request: web.Request) -> web.Response:
        return web.json_response(self._build_agents_list())

    async def _api_agent_detail(self, request: web.Request) -> web.Response:
        agent_id = request.match_info["agent_id"]
        status = self._tracker.get_status(agent_id)
        return web.json_response({"id": agent_id, **status})

    async def _api_agent_message(self, request: web.Request) -> web.Response:
        agent_id = request.match_info["agent_id"]
        data = await request.json()
        text = data.get("text", "")
        asyncio.create_task(self._process_message(agent_id, text))
        return web.json_response({"ok": True, "agent": agent_id})

    async def _api_agent_trigger(self, request: web.Request) -> web.Response:
        agent_id = request.match_info["agent_id"]
        data = await request.json()
        job_id = data.get("job_id", "")
        self._tracker.on_working(agent_id, f"Running: {job_id}")
        await self._broadcast({
            "type": "cron_event",
            "agent": agent_id,
            "job": job_id,
            "action": "started",
        })
        return web.json_response({"ok": True, "agent": agent_id, "job_id": job_id})

    async def _api_cron(self, request: web.Request) -> web.Response:
        return web.json_response(self._cron_jobs)

    async def _api_weather(self, request: web.Request) -> web.Response:
        return web.json_response({"type": "sunny", "since": 0, "next_change": 0})

    async def _api_save_layout(self, request: web.Request) -> web.Response:
        data = await request.json()
        self._save_layout(data.get("buildings", []))
        return web.json_response({"ok": True})

    # ── Broadcast ──

    async def _broadcast(self, msg: dict) -> None:
        for ws in list(self._ws_clients):
            if not ws.closed:
                try:
                    await ws.send_json(msg)
                except Exception:
                    self._ws_clients.discard(ws)

    def _on_status_change(self, agent_id: str, state: AgentState) -> None:
        msg = {
            "type": "agent_status",
            "agent": agent_id,
            "status": state.status,
            "detail": state.detail,
            "since": state.since,
        }
        for ws in list(self._ws_clients):
            if not ws.closed:
                asyncio.create_task(ws.send_json(msg))

    # ── Helpers ──

    def _build_agents_list(self) -> list[dict]:
        statuses = self._tracker.get_all_statuses()
        return [{"id": aid, "name": aid, **info} for aid, info in statuses.items()]

    def _load_layout(self) -> list[dict]:
        if self._layout_file.exists():
            return json.loads(self._layout_file.read_text())
        return []

    def _save_layout(self, buildings: list[dict]) -> None:
        self._layout_file.parent.mkdir(parents=True, exist_ok=True)
        self._layout_file.write_text(json.dumps(buildings, indent=2))

    @staticmethod
    def _current_season() -> str:
        import datetime
        month = datetime.datetime.now().month
        if 3 <= month <= 5:
            return "spring"
        if 6 <= month <= 8:
            return "summer"
        if 9 <= month <= 11:
            return "autumn"
        return "winter"


# ── Singleton & Lifecycle ──────────────────────────────────────────────────

_gateway: PixelTownGateway | None = None
_tracker: AgentStatusTracker | None = None


def get_tracker() -> AgentStatusTracker:
    """Get or create the global status tracker."""
    global _tracker
    if _tracker is None:
        _tracker = AgentStatusTracker([])
    return _tracker


async def start_pixeltown_server() -> None:
    """Start the PixelTown gateway. Runs until cancelled."""
    global _gateway
    cfg = get_config().gateway.pixeltown

    tracker = get_tracker()
    _gateway = PixelTownGateway(
        tracker,
        host=cfg.host,
        port=cfg.port,
        static_dir=cfg.static_dir,
        layout_file=cfg.layout_file,
    )

    app = web.Application()
    app.router.add_get("/ws", _gateway._ws_handler)
    app.router.add_get("/api/agents", _gateway._api_agents)
    app.router.add_get("/api/agents/{agent_id}", _gateway._api_agent_detail)
    app.router.add_post("/api/agents/{agent_id}/message", _gateway._api_agent_message)
    app.router.add_post("/api/agents/{agent_id}/trigger", _gateway._api_agent_trigger)
    app.router.add_get("/api/cron", _gateway._api_cron)
    app.router.add_get("/api/weather", _gateway._api_weather)
    app.router.add_put("/api/town/layout", _gateway._api_save_layout)

    # Serve frontend static files
    static_dir = Path(cfg.static_dir)
    if static_dir.exists():
        app.router.add_static("/", static_dir, name="static")
    else:
        log.warning("Static dir %s not found — run 'cd pixeltown && npm run build'", static_dir)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, cfg.host, cfg.port)
    await site.start()
    log.info("PixelTown gateway at http://%s:%d", cfg.host, cfg.port)

    try:
        await asyncio.Event().wait()
    finally:
        await runner.cleanup()
