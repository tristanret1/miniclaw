"""Agent abstraction — bundles per-bot identity, workspace, and runtime state."""

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


async def _load_from_db() -> list[Agent] | None:
    """Try to load agents from PostgreSQL. Returns None if not available."""
    from bot.storage.db import use_postgres, get_pool

    if not use_postgres():
        return None

    try:
        pool = await get_pool()
    except Exception as e:
        log.warning("failed to connect to PostgreSQL for agent loading: %s", e)
        return None

    if pool is None:
        return None

    agents = []
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, display_name, emoji, config, enabled FROM agents WHERE enabled = true"
        )

        for row in rows:
            import json as _json
            config_raw = row["config"]
            config_dict = _json.loads(config_raw) if isinstance(config_raw, str) else dict(config_raw)

            discord_cfg = config_dict.get("discord", {})
            discord_token = discord_cfg.get("bot_token", "")

            llm_cfg = config_dict.get("llm", {})
            provider = llm_cfg.get("provider", "")
            model = ""
            if provider == "codex":
                model = llm_cfg.get("codex", {}).get("model", "")
            elif provider == "anthropic":
                model = llm_cfg.get("anthropic", {}).get("model", "")

            # Load latest documents
            soul = identity = user_doc = ""
            for doc_type in ("soul", "identity", "user_doc"):
                doc_row = await conn.fetchrow(
                    """SELECT content FROM agent_documents
                       WHERE agent_id = $1 AND doc_type = $2
                       ORDER BY version DESC LIMIT 1""",
                    row["id"], doc_type,
                )
                if doc_row:
                    if doc_type == "soul":
                        soul = doc_row["content"]
                    elif doc_type == "identity":
                        identity = doc_row["content"]
                    else:
                        user_doc = doc_row["content"]

            # Build system prompt
            parts = [p for p in (soul, identity, user_doc) if p.strip()]
            if not parts:
                parts = ["You are a helpful assistant."]

            from bot.config import SKILLS_DIR
            from bot.skills import load_skills, build_skills_prompt
            skills = load_skills(SKILLS_DIR)
            skills_prompt = build_skills_prompt(skills)
            if skills_prompt:
                parts.append(skills_prompt)

            system_prompt = "\n\n---\n\n".join(parts)

            workspace_dir = PROJECT_ROOT / f"workspace_{row['name']}"
            workspace_dir.mkdir(parents=True, exist_ok=True)

            agents.append(Agent(
                name=row["name"],
                discord_token=discord_token,
                workspace_dir=workspace_dir,
                system_prompt=system_prompt,
                model=model,
                provider=provider,
            ))
            log.info("loaded agent '%s' from DB", row["name"])

    return agents if agents else None


async def load_agents_async(only: list[str] | None = None) -> list[Agent]:
    """Load agents from DB. Falls back to single default agent from .env."""
    agents = await _load_from_db()

    if agents:
        log.info("loaded %d agent(s) from database", len(agents))
    else:
        from bot.config import get_secrets, WORKSPACE_DIR, get_system_prompt
        log.info("no agents in DB, using default agent from .env")
        agents = [Agent(
            name="default",
            discord_token=get_secrets()["DISCORD_BOT_TOKEN"],
            workspace_dir=WORKSPACE_DIR,
            system_prompt=get_system_prompt(),
        )]

    if only:
        names = {n.lower() for n in only}
        agents = [a for a in agents if a.name.lower() in names]
        if not agents:
            raise SystemExit(f"No matching agents for --only {', '.join(only)}")

    if not agents:
        raise SystemExit("No enabled agents found. Check DB or .env.")

    return agents
