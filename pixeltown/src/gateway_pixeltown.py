"""PixelTown WebSocket + REST gateway — aiohttp server."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    from .status import AgentStatusTracker, AgentState

logger = logging.getLogger(__name__)


class PixelTownGateway:
    """
    aiohttp server providing:
      - Static file serving: pixeltown/dist/ at /
      - WebSocket endpoint: /ws
      - REST API: /api/*

    Launched as additional async task from main.py.
    """

    def __init__(
        self,
        status_tracker: "AgentStatusTracker",
        *,
        host: str = "127.0.0.1",
        port: int = 8765,
        static_dir: str = "pixeltown/dist",
        layout_file: str = "workspace/town_layout.json",
    ) -> None:
        self._tracker = status_tracker
        self._host = host
        self._port = port
        self._static_dir = Path(static_dir)
        self._layout_file = Path(layout_file)
        self._ws_clients: set[web.WebSocketResponse] = set()
        self._app: web.Application | None = None

        # Cron jobs list (set by main.py after scheduler init)
        self._cron_jobs: list[dict] = []

        # Register as status listener to push updates to WS clients
        self._tracker.add_listener(self._on_status_change)

    async def start(self) -> None:
        """Start the aiohttp server."""
        self._app = web.Application()
        self._app.router.add_get("/ws", self._ws_handler)
        self._app.router.add_get("/api/agents", self._api_agents)
        self._app.router.add_get("/api/agents/{agent_id}", self._api_agent_detail)
        self._app.router.add_post(
            "/api/agents/{agent_id}/message", self._api_agent_message
        )
        self._app.router.add_post(
            "/api/agents/{agent_id}/trigger", self._api_agent_trigger
        )
        self._app.router.add_get("/api/cron", self._api_cron)
        self._app.router.add_get("/api/weather", self._api_weather)
        self._app.router.add_put("/api/town/layout", self._api_save_layout)

        # Static files (must be last — catches all other routes)
        if self._static_dir.exists():
            self._app.router.add_static("/", self._static_dir, name="static")

        runner = web.AppRunner(self._app)
        await runner.setup()
        site = web.TCPSite(runner, self._host, self._port)
        await site.start()
        logger.info(
            "PixelTown gateway running at http://%s:%d", self._host, self._port
        )

    def set_cron_jobs(self, jobs: list[dict]) -> None:
        """Set cron jobs list (called by main.py after scheduler init)."""
        self._cron_jobs = jobs

    # ── WebSocket ──

    async def _ws_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        self._ws_clients.add(ws)

        # Send init message
        init_data = {
            "type": "init",
            "agents": self._build_agents_list(),
            "weather": {"type": "sunny", "since": 0, "next_change": 0},
            "season": self._current_season(),
            "town_layout": self._load_layout(),
            "affinity": self._tracker.get_all_affinities(),
        }
        await ws.send_json(init_data)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self._handle_ws_message(ws, json.loads(msg.data))
                elif msg.type == web.WSMsgType.ERROR:
                    logger.warning("WS error: %s", ws.exception())
        finally:
            self._ws_clients.discard(ws)

        return ws

    async def _handle_ws_message(
        self, ws: web.WebSocketResponse, data: dict
    ) -> None:
        msg_type = data.get("type")
        if msg_type == "save_layout":
            self._save_layout(data.get("buildings", []))
        elif msg_type == "send_message":
            agent_id = data.get("agent", "")
            text = data.get("text", "")
            logger.info("Send message to %s: %s", agent_id, text)
            # Broadcast message_received to all clients
            await self._broadcast(
                {
                    "type": "message_received",
                    "agent": agent_id,
                    "from": "user",
                    "preview": text[:80],
                }
            )
        elif msg_type == "trigger_task":
            agent_id = data.get("agent", "")
            job_id = data.get("job_id", "")
            logger.info("Trigger task %s for %s", job_id, agent_id)
            # Set agent to working + broadcast cron_event
            self._tracker.on_working(agent_id, f"Running: {job_id}")
            await self._broadcast(
                {
                    "type": "cron_event",
                    "agent": agent_id,
                    "job": job_id,
                    "action": "started",
                }
            )
        elif msg_type == "toggle_agent":
            agent_id = data.get("agent", "")
            enabled = data.get("enabled", True)
            logger.info("Toggle agent %s: enabled=%s", agent_id, enabled)
            if enabled:
                self._tracker.on_online(agent_id)
            else:
                self._tracker.on_offline(agent_id)

    # ── REST API ──

    async def _api_agents(self, request: web.Request) -> web.Response:
        return web.json_response(self._build_agents_list())

    async def _api_agent_detail(self, request: web.Request) -> web.Response:
        agent_id = request.match_info["agent_id"]
        status = self._tracker.get_status(agent_id)
        return web.json_response({"id": agent_id, **status})

    async def _api_agent_message(self, request: web.Request) -> web.Response:
        """POST /api/agents/{agent_id}/message — send message to agent."""
        agent_id = request.match_info["agent_id"]
        data = await request.json()
        text = data.get("text", "")
        logger.info("REST: Send message to %s: %s", agent_id, text)
        await self._broadcast(
            {
                "type": "message_received",
                "agent": agent_id,
                "from": "user",
                "preview": text[:80],
            }
        )
        return web.json_response({"ok": True, "agent": agent_id})

    async def _api_agent_trigger(self, request: web.Request) -> web.Response:
        """POST /api/agents/{agent_id}/trigger — trigger a cron job."""
        agent_id = request.match_info["agent_id"]
        data = await request.json()
        job_id = data.get("job_id", "")
        logger.info("REST: Trigger task %s for %s", job_id, agent_id)
        self._tracker.on_working(agent_id, f"Running: {job_id}")
        await self._broadcast(
            {
                "type": "cron_event",
                "agent": agent_id,
                "job": job_id,
                "action": "started",
            }
        )
        return web.json_response({"ok": True, "agent": agent_id, "job_id": job_id})

    async def _api_cron(self, request: web.Request) -> web.Response:
        """GET /api/cron — list scheduled cron jobs."""
        return web.json_response(self._cron_jobs)

    async def _api_weather(self, request: web.Request) -> web.Response:
        return web.json_response({"type": "sunny", "since": 0, "next_change": 0})

    async def _api_save_layout(self, request: web.Request) -> web.Response:
        data = await request.json()
        self._save_layout(data.get("buildings", []))
        return web.json_response({"ok": True})

    # ── Broadcast ──

    async def _broadcast(self, msg: dict) -> None:
        """Send a message to all connected WS clients."""
        for ws in list(self._ws_clients):
            if not ws.closed:
                try:
                    await ws.send_json(msg)
                except Exception:
                    self._ws_clients.discard(ws)

    # ── Status change broadcast ──

    def _on_status_change(self, agent_id: str, state: "AgentState") -> None:
        """Push status update to all connected WS clients."""
        import asyncio

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
        return [
            {"id": aid, "name": aid, **info} for aid, info in statuses.items()
        ]

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
