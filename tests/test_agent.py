"""Tests for bot.agent — Agent dataclass and properties."""

from pathlib import Path
from bot.agent import Agent


class TestAgent:
    def test_post_init_builds_system_prompt(self, tmp_path):
        """Agent without explicit system_prompt builds one from workspace."""
        ws = tmp_path / "workspace"
        ws.mkdir()
        (ws / "SOUL.md").write_text("Be kind.")
        (ws / "IDENTITY.md").write_text("Name: TestBot")
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws)
        assert "Be kind" in agent.system_prompt
        assert "TestBot" in agent.system_prompt

    def test_memory_dir_created(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws, system_prompt="hi")
        mem_dir = agent.memory_dir
        assert mem_dir.exists()
        assert mem_dir == ws / "memory"

    def test_sessions_db_path(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws, system_prompt="hi")
        assert agent.sessions_db == ws / "sessions.db"

    def test_effective_model_override(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws,
                      system_prompt="hi", model="custom-model")
        assert agent.effective_model == "custom-model"

    def test_effective_provider_override(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws,
                      system_prompt="hi", provider="codex")
        assert agent.effective_provider == "codex"

    def test_effective_model_default(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws,
                      system_prompt="hi")
        # Should fall back to global config default
        model = agent.effective_model
        assert isinstance(model, str)
        assert len(model) > 0

    def test_effective_provider_default(self, tmp_path):
        ws = tmp_path / "workspace"
        ws.mkdir()
        agent = Agent(name="test", discord_token="fake", workspace_dir=ws,
                      system_prompt="hi")
        provider = agent.effective_provider
        assert provider in ("anthropic", "codex")
