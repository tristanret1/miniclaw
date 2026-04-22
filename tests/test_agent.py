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

    def test_effective_model_follows_provider(self, tmp_path, monkeypatch):
        """effective_model must read from the cfg section matching cfg.llm.provider."""
        from bot.config import reset_config
        from bot.config_schema import AppConfig
        import bot.config as cfg_mod

        ws = tmp_path / "workspace"
        ws.mkdir()
        for provider, expected in [
            ("kimi", "kimi-for-coding"),
            ("glm", "glm-4.7-flash"),
            ("codex", "gpt-5.3-codex"),
            ("minimax", "MiniMax-M2.7"),
            ("anthropic", "claude-sonnet-4-20250514"),
        ]:
            cfg = AppConfig.from_dict({"llm": {"provider": provider}})
            monkeypatch.setattr(cfg_mod, "_config", cfg)
            try:
                agent = Agent(name="t", discord_token="fake",
                              workspace_dir=ws, system_prompt="hi")
                assert agent.effective_model == expected, \
                    f"provider={provider}: got {agent.effective_model}"
            finally:
                reset_config()
