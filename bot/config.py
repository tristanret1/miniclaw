import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))
TOOLS_ENABLED = os.getenv("TOOLS_ENABLED", "true").lower() in ("true", "1", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # for embedding (text-embedding-3-small)

# Claude Code integration (via claude-agent-sdk)
ACP_CWD = os.getenv("ACP_CWD", "")  # default working directory for Claude Code tasks

# GitHub token for gh CLI and git push
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"

# Bootstrap files injected into system prompt, same order as openclaw
_BOOTSTRAP_FILES = ["SOUL.md", "IDENTITY.md"]


def build_system_prompt() -> str:
    """Build system prompt by reading workspace bootstrap files."""
    parts: list[str] = []

    for filename in _BOOTSTRAP_FILES:
        filepath = WORKSPACE_DIR / filename
        if filepath.exists():
            content = filepath.read_text().strip()
            if content:
                parts.append(content)

    if not parts:
        return "You are a helpful assistant."

    return "\n\n---\n\n".join(parts)


SYSTEM_PROMPT = build_system_prompt()

# Auto-reply settings
AUTO_REPLY_ENABLED = os.getenv("AUTO_REPLY_ENABLED", "false").lower() in ("true", "1", "yes")
AUTO_REPLY_CHANNELS = os.getenv("AUTO_REPLY_CHANNELS", "").split(",")  # Channel IDs where auto-reply is allowed
AUTO_REPLY_CHANCE = float(os.getenv("AUTO_REPLY_CHANCE", "0.1"))  # 0.1 = 10% chance to reply
AUTO_REPLY_KEYWORDS = os.getenv("AUTO_REPLY_KEYWORDS", "").split(",")  # Keywords that trigger auto-reply
