import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "20"))

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
