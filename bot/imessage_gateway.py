"""iMessage gateway — uses `imsg` CLI via JSON-RPC over stdio.

Spawns `imsg rpc` as a subprocess, listens for inbound message notifications,
processes them through Claude, and sends replies back via the same RPC channel.

Reference: openclaw/extensions/imessage/src/client.ts
"""

import asyncio
import json
from typing import Any

from bot.config import (
    IMESSAGE_CLI_PATH,
    IMESSAGE_DB_PATH,
    IMESSAGE_ALLOW_FROM,
    IMESSAGE_SERVICE,
)
from bot.logger import get_logger
from bot.message import build_user_content

log = get_logger("imessage")


# ── JSON-RPC client ─────────────────────────────────────────────────────────

class IMessageRpcClient:
    """JSON-RPC 2.0 client that communicates with `imsg rpc` over stdio."""

    def __init__(self, cli_path: str = "imsg", db_path: str = ""):
        self._cli_path = cli_path
        self._db_path = db_path
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._pending: dict[str, asyncio.Future] = {}
        self._on_notification: Any = None  # callback(method, params)
        self._reader_task: asyncio.Task | None = None

    async def start(self, on_notification=None) -> None:
        """Spawn `imsg rpc` and start reading stdout."""
        if self._process:
            return

        self._on_notification = on_notification
        args = [self._cli_path, "rpc"]
        if self._db_path:
            args.extend(["--db", self._db_path])

        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        asyncio.create_task(self._stderr_loop())
        log.info("imsg rpc started (pid=%d)", self._process.pid)

    async def stop(self) -> None:
        """Gracefully stop the imsg rpc process."""
        if not self._process:
            return

        if self._process.stdin:
            self._process.stdin.close()

        # Give it a moment to exit
        try:
            await asyncio.wait_for(self._process.wait(), timeout=2.0)
        except asyncio.TimeoutError:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                self._process.kill()

        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        # Fail all pending requests
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(RuntimeError("imsg rpc closed"))
        self._pending.clear()

        self._process = None
        log.info("imsg rpc stopped")

    async def request(self, method: str, params: dict | None = None, timeout: float = 30.0) -> Any:
        """Send a JSON-RPC request and wait for the response."""
        if not self._process or not self._process.stdin:
            raise RuntimeError("imsg rpc not running")

        req_id = str(self._next_id)
        self._next_id += 1

        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params or {},
        }
        line = json.dumps(payload) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[req_id] = fut

        try:
            return await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(req_id, None)
            raise RuntimeError(f"imsg rpc timeout ({method})")

    async def _read_loop(self) -> None:
        """Read stdout line by line and dispatch responses/notifications."""
        assert self._process and self._process.stdout
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    break  # EOF — process exited
                self._handle_line(line.decode().strip())
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error("imsg rpc read error: %s", e)
        finally:
            # Fail remaining pending requests
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(RuntimeError("imsg rpc closed"))
            self._pending.clear()

    async def _stderr_loop(self) -> None:
        """Log stderr output from imsg rpc."""
        assert self._process and self._process.stderr
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    break
                log.debug("imsg stderr: %s", line.decode().strip())
        except (asyncio.CancelledError, Exception):
            pass

    def _handle_line(self, line: str) -> None:
        """Parse a JSON-RPC response or notification."""
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            log.warning("imsg rpc: invalid JSON: %s", line[:200])
            return

        # Response to a request
        msg_id = msg.get("id")
        if msg_id is not None:
            key = str(msg_id)
            fut = self._pending.pop(key, None)
            if fut and not fut.done():
                if "error" in msg:
                    err = msg["error"]
                    fut.set_exception(RuntimeError(
                        err.get("message", "imsg rpc error")
                    ))
                else:
                    fut.set_result(msg.get("result"))
            return

        # Notification (no id)
        method = msg.get("method")
        if method and self._on_notification:
            try:
                self._on_notification(method, msg.get("params"))
            except Exception as e:
                log.error("notification handler error: %s", e)


# ── Message processing ──────────────────────────────────────────────────────

def _normalize_handle(handle: str) -> str:
    """Normalize phone/email handle for session keys."""
    h = handle.strip().lower()
    # Strip service prefix like "imessage:" or "sms:"
    if ":" in h and not h.startswith("+"):
        h = h.split(":", 1)[1]
    return h


def _is_allowed(sender: str) -> bool:
    """Check if sender is in allowlist (empty = allow all)."""
    if not IMESSAGE_ALLOW_FROM:
        return True
    normalized = _normalize_handle(sender)
    for allowed in IMESSAGE_ALLOW_FROM:
        if _normalize_handle(allowed) == normalized:
            return True
    return False


async def _process_message(client: IMessageRpcClient, sender: str, text: str, chat_id: int | None = None) -> None:
    """Process an inbound iMessage and reply."""
    try:
        session_key = f"imessage:{_normalize_handle(sender)}"
        user_content = build_user_content(text or "(empty message)", [])

        from bot import llm
        reply_text = await llm.reply(session_key, user_content)

        if reply_text.strip():
            await send_imessage(client, to=sender, message=reply_text, chat_id=chat_id)
    except Exception:
        log.exception("iMessage processing failed for %s", sender)


async def send_imessage(
    client: IMessageRpcClient,
    to: str,
    message: str,
    chat_id: int | None = None,
    service: str | None = None,
) -> str:
    """Send an iMessage via the RPC client."""
    params: dict[str, Any] = {
        "text": message,
        "service": service or IMESSAGE_SERVICE,
    }
    if chat_id:
        params["chat_id"] = chat_id
    else:
        params["to"] = to

    try:
        result = await client.request("send", params)
        msg_id = "unknown"
        if isinstance(result, dict):
            msg_id = result.get("messageId") or result.get("message_id") or result.get("id") or result.get("ok", "unknown")
        log.info("imessage → %s (id=%s)", to, msg_id)
        return f"iMessage sent to {to} (id={msg_id})"
    except Exception as e:
        log.error("imessage send failed to %s: %s", to, e)
        return f"Error sending iMessage: {e}"


# ── Standalone send (for tools, no persistent client) ────────────────────────

async def run_imessage_send(to: str, message: str) -> str:
    """Send an iMessage using a temporary RPC client. Used by tool dispatch."""
    client = IMessageRpcClient(cli_path=IMESSAGE_CLI_PATH, db_path=IMESSAGE_DB_PATH)
    try:
        await client.start()
        return await send_imessage(client, to=to, message=message)
    finally:
        await client.stop()


# ── Gateway lifecycle ────────────────────────────────────────────────────────

# Module-level client for reuse by tools when gateway is running
_gateway_client: IMessageRpcClient | None = None


def get_gateway_client() -> IMessageRpcClient | None:
    """Return the running gateway client, if any."""
    return _gateway_client


async def start_imessage_gateway() -> None:
    """Start the iMessage gateway. Listens for inbound messages via imsg rpc.
    Runs until cancelled."""
    global _gateway_client

    client = IMessageRpcClient(cli_path=IMESSAGE_CLI_PATH, db_path=IMESSAGE_DB_PATH)
    _gateway_client = client

    message_queue: asyncio.Queue = asyncio.Queue()

    def on_notification(method: str, params: Any) -> None:
        """Handle inbound message notifications from imsg rpc."""
        log.debug("imsg notification: method=%s params=%s", method, str(params)[:300])
        if method == "message":
            # Queue for async processing
            message_queue.put_nowait(params)

    await client.start(on_notification=on_notification)
    log.info("iMessage gateway started (cli=%s)", IMESSAGE_CLI_PATH)

    # Subscribe to incoming messages — imsg rpc won't push notifications without this
    sub_id = None
    try:
        sub_result = await client.request("watch.subscribe", {"attachments": False})
        sub_id = sub_result.get("subscription") if isinstance(sub_result, dict) else None
        log.info("iMessage watch subscribed (subscription=%s)", sub_id)
    except Exception as e:
        log.error("iMessage watch.subscribe failed: %s", e)

    try:
        while True:
            params = await message_queue.get()
            if not isinstance(params, dict):
                continue

            # imsg rpc wraps the payload in {"message": {...}}
            msg = params.get("message", params) if isinstance(params.get("message"), dict) else params

            sender = msg.get("sender") or msg.get("handle") or msg.get("from", "")
            text = msg.get("text") or msg.get("body") or ""
            is_from_me = msg.get("is_from_me", False)
            chat_id = msg.get("chat_id")

            # Skip our own messages
            if is_from_me:
                continue

            if not sender:
                log.debug("imessage: skipping message with no sender")
                continue

            if not _is_allowed(sender):
                log.info("imessage: blocked message from %s (not in allowlist)", sender)
                continue

            log.info("imessage ← from=%s len=%d", sender, len(text))
            asyncio.create_task(_process_message(client, sender, text, chat_id))

    except asyncio.CancelledError:
        pass
    finally:
        if sub_id is not None:
            try:
                await client.request("watch.unsubscribe", {"subscription": sub_id}, timeout=3.0)
            except Exception:
                pass
        _gateway_client = None
        await client.stop()
        log.info("iMessage gateway stopped")
