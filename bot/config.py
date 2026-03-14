import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
TOOLS_ENABLED = os.getenv("TOOLS_ENABLED", "true").lower() in ("true", "1", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # for embedding (text-embedding-3-small)

# Claude Code integration (via claude-agent-sdk)
ACP_CWD = os.getenv("ACP_CWD", "")  # default working directory for Claude Code tasks

# GitHub token for gh CLI and git push
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Web search (Brave Search API)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"
SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Bootstrap files injected into system prompt, same order as openclaw
_BOOTSTRAP_FILES = ["SOUL.md", "IDENTITY.md"]


def build_system_prompt() -> str:
    """Build system prompt by reading workspace bootstrap files + skills."""
    parts: list[str] = []

    for filename in _BOOTSTRAP_FILES:
        filepath = WORKSPACE_DIR / filename
        if filepath.exists():
            content = filepath.read_text().strip()
            if content:
                parts.append(content)

    if not parts:
        parts.append("You are a helpful assistant.")

    # Inject skills into system prompt
    from bot.skills import load_skills, build_skills_prompt
    skills = load_skills(SKILLS_DIR)
    skills_prompt = build_skills_prompt(skills)
    if skills_prompt:
        parts.append(skills_prompt)

    return "\n\n---\n\n".join(parts)


def get_loaded_skills():
    """Return loaded skills (cached after first system prompt build)."""
    from bot.skills import load_skills
    return load_skills(SKILLS_DIR)


SYSTEM_PROMPT = build_system_prompt()

# Auto-reply settings
AUTO_REPLY_ENABLED = os.getenv("AUTO_REPLY_ENABLED", "false").lower() in ("true", "1", "yes")
AUTO_REPLY_CHANNELS = os.getenv("AUTO_REPLY_CHANNELS", "").split(",")  # Channel IDs where auto-reply is allowed
AUTO_REPLY_CHANCE = float(os.getenv("AUTO_REPLY_CHANCE", "0.1"))  # 0.1 = 10% chance to reply
AUTO_REPLY_KEYWORDS = os.getenv("AUTO_REPLY_KEYWORDS", "").split(",")  # Keywords that trigger auto-reply

# Session scope: user_in_channel (default), channel, or thread
SESSION_SCOPE = os.getenv("SESSION_SCOPE", "user_in_channel")

# Cron scheduler
CRON_ENABLED = os.getenv("CRON_ENABLED", "true").lower() in ("true", "1", "yes")
CRON_TIMEZONE = os.getenv("CRON_TIMEZONE", "America/Vancouver")
CRON_MAX_CONCURRENT = int(os.getenv("CRON_MAX_CONCURRENT", "5"))

# History window budget (approx chars, ~4 chars per token). Used to
# construct a rolling window for the model input instead of a fixed
# count of messages.
HISTORY_CHAR_BUDGET = int(os.getenv("HISTORY_CHAR_BUDGET", str(120_000)))
