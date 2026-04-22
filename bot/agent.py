"""Single agent — Peter.

No multi-agent routing. One workspace, one identity, shared across all channels.
"""

from dataclasses import dataclass, field
from pathlib import Path

from bot.logger import get_logger

log = get_logger("agent")

PROJECT_ROOT = Path(__file__).parent.parent

AGENT_NAME = "peter"


@dataclass
class Agent:
    """The single bot agent with its workspace and runtime state."""

    name: str = AGENT_NAME
    discord_token: str = ""
    workspace_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "workspace")
    system_prompt: str = ""
    model: str = ""
    provider: str = ""

    # Runtime state (set during startup)
    session_mgr: object = field(default=None, repr=False)  # SessionManager

    def __post_init__(self):
        self.workspace_dir = Path(self.workspace_dir)
        if not self.system_prompt:
            from bot.config import build_system_prompt
            self.system_prompt = build_system_prompt(self.workspace_dir)

    @property
    def memory_dir(self) -> Path:
        d = self.workspace_dir / "memory"
        d.mkdir(parents=True, exist_ok=True)
        return d

    @property
    def sessions_db(self) -> Path:
        return self.workspace_dir / "sessions.db"

    @property
    def effective_model(self) -> str:
        if self.model:
            return self.model
        from bot.config import get_config
        cfg = get_config()
        provider_configs = {
            "anthropic": cfg.llm.anthropic,
            "codex": cfg.llm.codex,
            "glm": cfg.llm.glm,
            "minimax": cfg.llm.minimax,
            "kimi": cfg.llm.kimi,
        }
        pcfg = provider_configs.get(cfg.llm.provider) or cfg.llm.anthropic
        return pcfg.model

    @property
    def effective_provider(self) -> str:
        if self.provider:
            return self.provider
        from bot.config import get_config
        return get_config().llm.provider


def load_agent() -> Agent:
    """Create the single Peter agent from .env config."""
    from bot.config import get_secrets, WORKSPACE_DIR, get_system_prompt
    return Agent(
        name=AGENT_NAME,
        discord_token=get_secrets()["DISCORD_BOT_TOKEN"],
        workspace_dir=WORKSPACE_DIR,
        system_prompt=get_system_prompt(),
    )
