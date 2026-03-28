"""Configuration loader.

API:
  get_config()    → AppConfig (parsed from config.yaml, cached)
  get_secrets()   → dict of sensitive values from .env
  reset_config()  → clear cached AppConfig (used in tests)
  build_system_prompt() / get_system_prompt() / get_loaded_skills()

Path constants:
  PROJECT_ROOT, WORKSPACE_DIR, SKILLS_DIR
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── Project paths ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent
WORKSPACE_DIR: Path = PROJECT_ROOT / "workspace"
SKILLS_DIR: Path = PROJECT_ROOT / "skills"

# ── SECTION A: New lazy API ───────────────────────────────────────────────────

from bot.config_schema import AppConfig  # noqa: E402

_config: AppConfig | None = None
_system_prompt: str | None = None

_BOOTSTRAP_FILES = ["SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]


def get_config(config_path: Path | None = None) -> AppConfig:
    """Return the cached AppConfig, loading config.yaml on first call."""
    global _config
    if _config is not None:
        return _config
    path = config_path or PROJECT_ROOT / "config.yaml"
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    else:
        raw = {}
    _config = AppConfig.from_dict(raw)
    return _config


def reset_config() -> None:
    """Clear the cached AppConfig and system prompt (useful in tests)."""
    global _config, _system_prompt
    _config = None
    _system_prompt = None


def get_secrets() -> dict:
    """Return all sensitive config values loaded from .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    return {
        "DISCORD_BOT_TOKEN": os.getenv("DISCORD_BOT_TOKEN", ""),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY", ""),
        "DATABASE_URL": os.getenv("DATABASE_URL", ""),
        "GITHUB_TOKEN": os.getenv("GITHUB_TOKEN", ""),
        "ACP_CWD": os.getenv("ACP_CWD", ""),
        "TWILIO_ACCOUNT_SID": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "TWILIO_AUTH_TOKEN": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "TWILIO_FROM_NUMBER": os.getenv("TWILIO_FROM_NUMBER", ""),
        "VOLCENGINE_TTS_API_KEY": os.getenv("VOLCENGINE_TTS_API_KEY", ""),
        "GOOGLE_CALENDAR_CLIENT_ID": os.getenv("GOOGLE_CALENDAR_CLIENT_ID", ""),
        "GOOGLE_CALENDAR_CLIENT_SECRET": os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", ""),
        "GOOGLE_CALENDAR_LIFE_ID": os.getenv("GOOGLE_CALENDAR_LIFE_ID", ""),
        "GOOGLE_CALENDAR_WORK_ID": os.getenv("GOOGLE_CALENDAR_WORK_ID", ""),
    }


def build_system_prompt(workspace_dir: Path | None = None) -> str:
    """Build system prompt by reading workspace bootstrap files + skills."""
    ws = workspace_dir or WORKSPACE_DIR
    parts: list[str] = []

    for filename in _BOOTSTRAP_FILES:
        filepath = ws / filename
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


def get_system_prompt(workspace_dir: Path | None = None) -> str:
    """Return the cached system prompt, building it on first call."""
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = build_system_prompt(workspace_dir)
    return _system_prompt


def get_loaded_skills():
    """Return loaded skills (re-reads from disk each call)."""
    from bot.skills import load_skills
    return load_skills(SKILLS_DIR)
