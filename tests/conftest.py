"""Shared test fixtures for MiniClaw."""

import json
import os
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock

import pytest

from bot.message import Message
from bot.provider.base import BaseProvider


# ── Environment setup (runs before any bot.* import) ─────────────────────────

def pytest_configure(config):
    """Set fake env vars before test collection triggers module imports."""
    defaults = {
        "DISCORD_BOT_TOKEN": "test-token-fake",
        "CLAUDE_MODEL": "claude-test",
        "MAX_HISTORY": "10",
        "TOOLS_ENABLED": "true",
        "OPENAI_API_KEY": "",
        "ACP_CWD": "/tmp/test",
        "GITHUB_TOKEN": "",
        "AUTO_REPLY_ENABLED": "false",
        "AUTO_REPLY_CHANNELS": "",
        "AUTO_REPLY_CHANCE": "0.0",
        "AUTO_REPLY_KEYWORDS": "",
        "PROVIDER": "anthropic",
        "CODEX_MODEL": "gpt-5.3-codex",
        "SMS_ENABLED": "false",
        "SMS_WEBHOOK_PORT": "8080",
        "SMS_WEBHOOK_URL": "",
        "IMESSAGE_ENABLED": "false",
        "IMESSAGE_CLI_PATH": "imsg",
        "IMESSAGE_DB_PATH": "",
        "IMESSAGE_ALLOW_FROM": "",
        "IMESSAGE_SERVICE": "auto",
    }
    for key, val in defaults.items():
        os.environ.setdefault(key, val)


# ── SQLite fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def session_db(tmp_path, monkeypatch):
    """Redirect session DB to a temp file."""
    import bot.session as session_mod
    db_path = tmp_path / "sessions.db"
    monkeypatch.setattr(session_mod, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(session_mod, "_conns", {})
    yield db_path
    # Reset global connections after test
    for conn in session_mod._conns.values():
        conn.close()
    session_mod._conns.clear()


@pytest.fixture
def memory_db(tmp_path, monkeypatch):
    """Redirect memory DB and log dir to temp."""
    import bot.memory as memory_mod
    db_path = tmp_path / "memory.db"
    mem_dir = tmp_path / "memory"
    mem_dir.mkdir()
    monkeypatch.setattr(memory_mod, "DB_PATH", db_path)
    monkeypatch.setattr(memory_mod, "DEFAULT_MEMORY_DIR", mem_dir)
    yield db_path, mem_dir


# ── Fake credentials ────────────────────────────────────────────────────────

@pytest.fixture
def fake_credentials(tmp_path, monkeypatch):
    """Write fake OAuth credentials to a temp path."""
    import bot.oauth as oauth_mod
    creds = {
        "access_token": "fake-access-token",
        "refresh_token": "fake-refresh-token",
        "expires_in": 28800,
    }
    creds_path = tmp_path / ".credentials.json"
    creds_path.write_text(json.dumps(creds))
    monkeypatch.setattr(oauth_mod, "CREDENTIALS_PATH", creds_path)
    yield creds, creds_path


# ── Fake LLM Provider ───────────────────────────────────────────────────────

class FakeProvider(BaseProvider):
    """A controllable provider for testing processor/llm logic."""

    def __init__(self, stream_events: list[list[dict]] | None = None, call_responses: list[dict] | None = None):
        # stream_events: list of rounds, each round is a list of SSE event dicts
        self._stream_rounds = list(stream_events or [])
        self._stream_round_idx = 0
        self._call_responses = list(call_responses or [])
        self._call_idx = 0

    async def stream(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> AsyncIterator[dict]:
        if self._stream_round_idx < len(self._stream_rounds):
            events = self._stream_rounds[self._stream_round_idx]
            self._stream_round_idx += 1
            for event in events:
                yield event
        else:
            return

    async def call(
        self,
        messages: list[Message],
        system: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> dict:
        if self._call_idx < len(self._call_responses):
            resp = self._call_responses[self._call_idx]
            self._call_idx += 1
            return resp
        return {"content": [], "stop_reason": "end_turn"}

    async def refresh_auth(self) -> None:
        pass


def make_text_stream_events(text: str) -> list[dict]:
    """Build a list of SSE events that stream a simple text response."""
    return [
        {"_event": "message_start", "message": {"role": "assistant"}},
        {"_event": "content_block_start", "content_block": {"type": "text", "text": ""}},
        {"_event": "content_block_delta", "delta": {"type": "text_delta", "text": text}},
        {"_event": "content_block_stop", "index": 0},
        {"_event": "message_delta", "delta": {"stop_reason": "end_turn"}},
    ]


def make_tool_use_stream_events(tool_id: str, tool_name: str, tool_input: dict) -> list[dict]:
    """Build SSE events for a tool_use response."""
    input_json = json.dumps(tool_input)
    return [
        {"_event": "message_start", "message": {"role": "assistant"}},
        {"_event": "content_block_start", "content_block": {
            "type": "tool_use", "id": tool_id, "name": tool_name,
        }},
        {"_event": "content_block_delta", "delta": {
            "type": "input_json_delta", "partial_json": input_json,
        }},
        {"_event": "content_block_stop", "index": 0},
        {"_event": "message_delta", "delta": {"stop_reason": "tool_use"}},
    ]


@pytest.fixture
def fake_provider():
    """Factory fixture for creating FakeProvider instances."""
    return FakeProvider


@pytest.fixture
def make_text_events():
    """Expose text stream event builder."""
    return make_text_stream_events


@pytest.fixture
def make_tool_events():
    """Expose tool use stream event builder."""
    return make_tool_use_stream_events
