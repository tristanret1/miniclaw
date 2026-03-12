"""ACP (Agent Client Protocol) client — communicate with Claude Code via JSON-RPC 2.0 over NDJSON/stdio."""

import asyncio
import json
import os
import shutil
from collections.abc import AsyncGenerator

from bot.config import ACP_COMMAND, ACP_CWD
from bot.logger import get_logger

log = get_logger("acp")

# Protocol version matching @agentclientprotocol/sdk
PROTOCOL_VERSION = "0.1"

# Permission auto-approve: read-only tools are always safe
SAFE_TOOLS = {"Read", "Glob", "Grep", "WebSearch", "WebFetch"}

# Max output to return to Claude (prevent context overflow)
MAX_OUTPUT_CHARS = 8000


class AcpClient:
    """Minimal ACP client that spawns and communicates with Claude Code."""

    def __init__(self, cwd: str | None = None):
        self.cwd = cwd or ACP_CWD or os.getcwd()
        self.process: asyncio.subprocess.Process | None = None
        self._req_id = 0
        self.session_id: str | None = None
        self._reader_task: asyncio.Task | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._notification_queue: asyncio.Queue = asyncio.Queue()

    async def start(self) -> None:
        """Spawn ACP server process and initialize a session."""
        cmd = _resolve_command()
        log.info("spawning ACP server: %s (cwd=%s)", " ".join(cmd), self.cwd)

        self.process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )

        # Start background reader for stdout
        self._reader_task = asyncio.create_task(self._read_loop())

        # Initialize handshake
        result = await self._request("initialize", {
            "protocolVersion": PROTOCOL_VERSION,
            "clientInfo": {"name": "miniclaw", "version": "0.1.0"},
            "clientCapabilities": {
                "fs": {"readTextFile": True, "writeTextFile": True},
                "terminal": True,
            },
        })
        agent_info = result.get("agentInfo", {})
        log.info("ACP initialized: %s %s", agent_info.get("name", "?"), agent_info.get("version", "?"))

        # Create a session
        session_result = await self._request("newSession", {
            "cwd": self.cwd,
            "mcpServers": [],
        })
        self.session_id = session_result.get("sessionId")
        log.info("ACP session created: %s", self.session_id)

    async def prompt(self, text: str, timeout: int = 300) -> str:
        """Send a prompt to Claude Code and collect the full response."""
        chunks = []
        async for chunk in self.prompt_stream(text, timeout=timeout):
            chunks.append(chunk)
        return "".join(chunks)

    async def prompt_stream(self, text: str, timeout: int = 300) -> AsyncGenerator[str, None]:
        """Send a prompt and yield text chunks as they arrive."""
        if not self.process or not self.session_id:
            await self.start()

        # Drain any old notifications
        while not self._notification_queue.empty():
            self._notification_queue.get_nowait()

        # Send prompt request (don't await response yet)
        req_id = self._next_id()
        await self._send(req_id, "prompt", {
            "sessionId": self.session_id,
            "prompt": [{"type": "text", "text": text}],
        })

        # Collect streaming notifications until we get the response
        tool_status: dict[str, str] = {}  # toolCallId -> title
        try:
            while True:
                try:
                    msg = await asyncio.wait_for(self._notification_queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    log.warning("ACP prompt timed out after %ds", timeout)
                    yield "\n[ACP timeout]"
                    return

                # Check if this is the final response
                if msg.get("id") == req_id:
                    stop = msg.get("result", {}).get("stopReason", "end_turn")
                    log.info("ACP prompt completed (stopReason=%s)", stop)
                    return

                # Handle notifications
                params = msg.get("params", {})
                update = params.get("sessionUpdate")

                if update == "agent_message_chunk":
                    content = params.get("content", {})
                    if content.get("type") == "text":
                        yield content["text"]

                elif update == "tool_call":
                    title = params.get("title", "tool")
                    tool_id = params.get("toolCallId", "")
                    tool_status[tool_id] = title
                    log.info("ACP tool: %s (status=%s)", title, params.get("status"))

                elif update == "tool_call_update":
                    tool_id = params.get("toolCallId", "")
                    title = tool_status.get(tool_id, "tool")
                    status = params.get("status", "?")
                    if status == "completed":
                        log.info("ACP tool done: %s", title)
                    elif status == "failed":
                        log.warning("ACP tool failed: %s", title)

                elif update == "permission_request":
                    # Auto-approve permissions
                    await self._handle_permission(params)

                elif update == "usage_update":
                    used = params.get("used", 0)
                    size = params.get("size", 0)
                    log.debug("ACP usage: %d/%d tokens", used, size)

        except Exception as e:
            log.error("ACP stream error: %s", e)
            yield f"\n[ACP error: {e}]"

    async def stop(self) -> None:
        """Terminate the ACP server process."""
        if self._reader_task:
            self._reader_task.cancel()
            self._reader_task = None

        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5)
            except (asyncio.TimeoutError, ProcessLookupError):
                self.process.kill()
            self.process = None
            self.session_id = None
            log.info("ACP server stopped")

    # ── Internal protocol methods ─────────────────────────────────────────────

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def _send(self, req_id: int, method: str, params: dict) -> None:
        """Send a JSON-RPC request."""
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        line = json.dumps(msg, ensure_ascii=False) + "\n"
        self.process.stdin.write(line.encode())
        await self.process.stdin.drain()
        log.debug("ACP → %s (id=%d)", method, req_id)

    async def _request(self, method: str, params: dict, timeout: int = 30) -> dict:
        """Send request and wait for the matching response."""
        req_id = self._next_id()
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = future
        await self._send(req_id, method, params)

        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        finally:
            self._pending.pop(req_id, None)

    async def _read_loop(self) -> None:
        """Background task: read NDJSON lines from stdout and dispatch."""
        try:
            while self.process and self.process.stdout:
                line = await self.process.stdout.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                msg_id = msg.get("id")

                if msg_id is not None and msg_id in self._pending:
                    # Response to a pending request
                    future = self._pending.pop(msg_id)
                    if msg.get("error"):
                        future.set_exception(RuntimeError(
                            f"ACP error: {msg['error'].get('message', msg['error'])}"
                        ))
                    else:
                        future.set_result(msg.get("result", {}))
                else:
                    # Notification or response for streaming prompt
                    await self._notification_queue.put(msg)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("ACP reader error: %s", e)

    async def _handle_permission(self, params: dict) -> None:
        """Auto-approve permission requests from Claude Code."""
        tool_name = params.get("toolName", "")
        permission_id = params.get("permissionId", "")

        # Auto-approve safe tools, approve others too (personal bot)
        approved = True
        log.info("ACP permission %s: %s → %s", permission_id, tool_name,
                 "approved" if approved else "denied")

        await self._send(self._next_id(), "permissionResponse", {
            "permissionId": permission_id,
            "approved": approved,
        })


# ── Module-level singleton ────────────────────────────────────────────────────

_client: AcpClient | None = None


async def get_client() -> AcpClient:
    """Get or create the singleton ACP client."""
    global _client
    if _client is None or _client.process is None or _client.process.returncode is not None:
        if _client:
            await _client.stop()
        _client = AcpClient()
        await _client.start()
    return _client


async def run_prompt(task: str, cwd: str | None = None, timeout: int = 300) -> str:
    """Send a coding task to Claude Code via ACP and return the result."""
    client = await get_client()
    if cwd and cwd != client.cwd:
        # Different working directory — restart with new cwd
        await client.stop()
        client = AcpClient(cwd=cwd)
        await client.start()
        global _client
        _client = client

    result = await client.prompt(task, timeout=timeout)

    # Truncate if too long
    if len(result) > MAX_OUTPUT_CHARS:
        result = result[:MAX_OUTPUT_CHARS] + f"\n... [truncated, {len(result)} chars total]"

    return result


async def shutdown() -> None:
    """Clean shutdown of ACP client."""
    global _client
    if _client:
        await _client.stop()
        _client = None


def _resolve_command() -> list[str]:
    """Resolve the ACP server command."""
    if ACP_COMMAND:
        return ACP_COMMAND.split()

    # Try to find claude-code-acp or claude CLI
    if shutil.which("claude"):
        # Claude Code CLI — use SDK subcommand if available
        return ["claude", "acp-serve"]

    # Fallback to npx
    return ["npx", "-y", "@anthropic-ai/claude-code-acp"]
