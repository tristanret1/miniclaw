"""Agent abstraction — bundles per-bot identity, workspace, and runtime state."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from bot.logger import get_logger

log = get_logger("agent")

PROJECT_ROOT = Path(__file__).parent.parent
AGENTS_JSON = PROJECT_ROOT / "agents.json"


@dataclass
class Agent:
    """A single agent identity with its own Discord bot, personality, and storage."""

    name: str
    discord_token: str
    workspace_dir: Path
    system_prompt: str = ""
    model: str = ""       # per-agent model override (empty = global default)
    provider: str = ""    # per-agent provider override (empty = global default)

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
        """Return per-agent model or fall back to global config."""
        if self.model:
            return self.model
        from bot.config import get_config
        cfg = get_config()
        if cfg.llm.provider == "codex":
            return cfg.llm.codex.model
        return cfg.llm.anthropic.model

    @property
    def effective_provider(self) -> str:
        """Return per-agent provider or fall back to global config."""
        if self.provider:
            return self.provider
        from bot.config import get_config
        return get_config().llm.provider


def _load_from_json() -> list[Agent] | None:
    """Try to load agents from agents.json. Returns None if file doesn't exist."""
    if not AGENTS_JSON.exists():
        return None

    log.info("loading agents from %s", AGENTS_JSON)
    with open(AGENTS_JSON) as f:
        data = json.load(f)

    entries = data.get("agents", [])
    if not entries:
        return None

    agents = []
    for entry in entries:
        name = entry.get("name", "").strip()
        token = entry.get("discord_token", "").strip()
        workspace = entry.get("workspace", f"workspace_{name}")

        if not name:
            log.warning("skipping agent entry with missing name: %s", entry)
            continue

        if not entry.get("enabled", True):
            log.info("agent '%s' is disabled, skipping", name)
            continue

        workspace_path = Path(workspace)
        if not workspace_path.is_absolute():
            workspace_path = PROJECT_ROOT / workspace_path

        workspace_path.mkdir(parents=True, exist_ok=True)

        agents.append(Agent(
            name=name,
            discord_token=token,
            workspace_dir=workspace_path,
            model=entry.get("model", ""),
            provider=entry.get("provider", ""),
        ))
        log.info("loaded agent '%s' (workspace=%s)", name, workspace_path)

    return agents if agents else None


def _load_from_env() -> list[Agent]:
    """Load agents from env vars (legacy). Falls back to single-agent mode."""
    from bot.config import get_secrets, WORKSPACE_DIR, get_system_prompt

    agents_str = os.getenv("AGENTS", "").strip()
    if not agents_str:
        # Single-agent backward compatibility
        return [Agent(
            name="default",
            discord_token=get_secrets()["DISCORD_BOT_TOKEN"],
            workspace_dir=WORKSPACE_DIR,
            system_prompt=get_system_prompt(),
        )]

    agents = []
    for name in agents_str.split(","):
        name = name.strip()
        if not name:
            continue

        key = name.upper()
        token = os.getenv(f"AGENT_{key}_DISCORD_TOKEN", "")
        workspace = os.getenv(f"AGENT_{key}_WORKSPACE", f"workspace_{name}")

        if not token:
            log.warning("agent '%s' has no AGENT_%s_DISCORD_TOKEN, skipping", name, key)
            continue

        workspace_path = Path(workspace)
        if not workspace_path.is_absolute():
            workspace_path = PROJECT_ROOT / workspace_path

        workspace_path.mkdir(parents=True, exist_ok=True)

        agents.append(Agent(
            name=name,
            discord_token=token,
            workspace_dir=workspace_path,
        ))
        log.info("loaded agent '%s' (workspace=%s)", name, workspace_path)

    if not agents:
        raise SystemExit("AGENTS is set but no valid agents found. Check AGENT_*_DISCORD_TOKEN vars.")

    return agents


def load_agents(only: list[str] | None = None) -> list[Agent]:
    """Load agents from agents.json first, falling back to .env.

    Args:
        only: If provided, only load agents whose names are in this list.
    """
    # Prefer agents.json
    agents = _load_from_json()
    if not agents:
        log.info("agents.json not found or empty, falling back to .env")
        agents = _load_from_env()

    if only:
        names = {n.lower() for n in only}
        agents = [a for a in agents if a.name.lower() in names]
        if not agents:
            raise SystemExit(f"No matching agents for --only {', '.join(only)}")

    if not agents:
        raise SystemExit("No enabled agents found. Check agents.json or .env.")

    return agents
