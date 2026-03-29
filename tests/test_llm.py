"""Tests for bot.llm — unified LLM entry point."""

from unittest.mock import patch, MagicMock

import bot.llm as llm_mod
from bot.storage.session import SessionManager
from tests.conftest import FakeProvider, make_text_stream_events


class TestLLM:
    async def test_stream_yields_chunks(self, session_db, monkeypatch):
        events = make_text_stream_events("Hello from LLM")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        monkeypatch.setattr(llm_mod, "_providers", {("_default", "_default"): provider})
        monkeypatch.setattr(llm_mod, "_default_session_mgr", session)

        chunks = []
        async for chunk in llm_mod.stream("test:1", "hi"):
            chunks.append(chunk)

        assert "".join(chunks) == "Hello from LLM"

    async def test_reply_collects_all_chunks(self, session_db, monkeypatch):
        events = make_text_stream_events("Complete reply")
        provider = FakeProvider(stream_events=[events])
        session = SessionManager()

        monkeypatch.setattr(llm_mod, "_providers", {("_default", "_default"): provider})
        monkeypatch.setattr(llm_mod, "_default_session_mgr", session)

        result = await llm_mod.reply("test:1", "hi")
        assert result == "Complete reply"

    async def test_singletons_created(self, monkeypatch):
        """Providers are created on first access and cached."""
        monkeypatch.setattr(llm_mod, "_providers", {})
        monkeypatch.setattr(llm_mod, "_default_session_mgr", None)

        provider = llm_mod._get_provider()
        session = llm_mod._get_default_session_mgr()

        assert provider is not None
        assert session is not None
        # Second call returns same instance
        assert llm_mod._get_provider() is provider
        assert llm_mod._get_default_session_mgr() is session

    async def test_singletons_reused(self, monkeypatch):
        """Multiple calls reuse the same provider and session."""
        monkeypatch.setattr(llm_mod, "_providers", {})
        monkeypatch.setattr(llm_mod, "_default_session_mgr", None)

        p1 = llm_mod._get_provider()
        p2 = llm_mod._get_provider()
        s1 = llm_mod._get_default_session_mgr()
        s2 = llm_mod._get_default_session_mgr()
        assert p1 is p2
        assert s1 is s2

    async def test_get_provider_with_specific_id_and_model(self, monkeypatch):
        """Specific provider_id + model creates and caches a separate provider."""
        monkeypatch.setattr(llm_mod, "_providers", {})
        p = llm_mod._get_provider("anthropic", "claude-sonnet-4-20250514")
        assert p is not None
        # Second call with same args returns cached instance
        p2 = llm_mod._get_provider("anthropic", "claude-sonnet-4-20250514")
        assert p is p2

    async def test_resolve_with_agent(self, monkeypatch):
        """_resolve with an Agent returns agent-specific values."""
        monkeypatch.setattr(llm_mod, "_providers", {})
        monkeypatch.setattr(llm_mod, "_default_session_mgr", None)

        mock_agent = MagicMock()
        mock_agent.session_mgr = None  # Should fall back to default
        mock_agent.effective_provider = "anthropic"
        mock_agent.effective_model = "claude-sonnet-4-20250514"
        mock_agent.system_prompt = "You are helpful."
        mock_agent.memory_dir = "/tmp/mem"
        mock_agent.name = "test-agent"

        provider, session, sys_prompt, mem_dir, name = llm_mod._resolve(mock_agent)
        assert provider is not None
        assert session is not None
        assert sys_prompt == "You are helpful."
        assert mem_dir == "/tmp/mem"
        assert name == "test-agent"
