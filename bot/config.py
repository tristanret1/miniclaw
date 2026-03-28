"""Configuration loader.

Two sections:

SECTION A — New API (lazy loading from config.yaml + .env secrets)
  get_config()    → AppConfig (parsed from config.yaml, cached)
  get_secrets()   → dict of sensitive values from .env
  reset_config()  → clear cached AppConfig (used in tests)
  build_system_prompt() / get_system_prompt() / get_loaded_skills()

SECTION B — Backward-compatible module-level names
  All existing os.getenv() names are preserved so that:
      from bot.config import DISCORD_BOT_TOKEN, CLAUDE_MODEL, ...
  continues to work without changes. These are loaded at import time from .env.
  TODO: migrate callers to get_config() / get_secrets() and remove this section.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

# ── Project paths ─────────────────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).parent.parent

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


# ── SECTION B: Backward-compatible module-level names ────────────────────────
# These are kept so existing `from bot.config import FOO` imports keep working.
# TODO: migrate callers to get_config() / get_secrets() and remove this section.

load_dotenv()

DISCORD_BOT_TOKEN: str = os.environ.get("DISCORD_BOT_TOKEN", "")
CLAUDE_MODEL: str = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CODEX_MODEL: str = os.getenv("CODEX_MODEL", "gpt-5.3-codex")
PROVIDER: str = os.getenv("PROVIDER", "anthropic")
MAX_HISTORY: int = int(os.getenv("MAX_HISTORY", "50"))
TOOLS_ENABLED: bool = os.getenv("TOOLS_ENABLED", "false").lower() in ("true", "1", "yes")
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

# PostgreSQL (Neon) — when set, all storage uses PostgreSQL instead of SQLite
DATABASE_URL: str = os.getenv("DATABASE_URL", "")

# Claude Code integration (via claude-agent-sdk)
ACP_CWD: str = os.getenv("ACP_CWD", "")

# GitHub token for gh CLI and git push
GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")

# Twilio (for phone_call tool)
TWILIO_ACCOUNT_SID: str = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN: str = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER: str = os.getenv("TWILIO_FROM_NUMBER", "")

WORKSPACE_DIR: Path = PROJECT_ROOT / "workspace"
SKILLS_DIR: Path = PROJECT_ROOT / "skills"

SYSTEM_PROMPT: str = build_system_prompt()

# Health tracking
HEALTH_TRACKING_ENABLED: bool = os.getenv("HEALTH_TRACKING_ENABLED", "true").lower() in ("true", "1", "yes")

# Google Calendar integration
GOOGLE_CALENDAR_ENABLED: bool = os.getenv("GOOGLE_CALENDAR_ENABLED", "false").lower() in ("true", "1", "yes")
GOOGLE_CALENDAR_CLIENT_ID: str = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET: str = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
GOOGLE_CALENDAR_LIFE_ID: str = os.getenv("GOOGLE_CALENDAR_LIFE_ID", "")
GOOGLE_CALENDAR_WORK_ID: str = os.getenv("GOOGLE_CALENDAR_WORK_ID", "")

# Cron scheduler
CRON_ENABLED: bool = os.getenv("CRON_ENABLED", "true").lower() in ("true", "1", "yes")
CRON_TIMEZONE: str = os.getenv("CRON_TIMEZONE", "America/Vancouver")
CRON_MAX_CONCURRENT: int = int(os.getenv("CRON_MAX_CONCURRENT", "5"))

# SMS gateway (Twilio inbound webhook)
SMS_ENABLED: bool = os.getenv("SMS_ENABLED", "false").lower() in ("true", "1", "yes")
SMS_WEBHOOK_PORT: int = int(os.getenv("SMS_WEBHOOK_PORT", "8080"))
SMS_WEBHOOK_URL: str = os.getenv("SMS_WEBHOOK_URL", "")

# iMessage gateway (via imsg CLI)
IMESSAGE_ENABLED: bool = os.getenv("IMESSAGE_ENABLED", "false").lower() in ("true", "1", "yes")
IMESSAGE_CLI_PATH: str = os.getenv("IMESSAGE_CLI_PATH", "imsg")
IMESSAGE_DB_PATH: str = os.getenv("IMESSAGE_DB_PATH", "")
IMESSAGE_ALLOW_FROM: list[str] = [s.strip() for s in os.getenv("IMESSAGE_ALLOW_FROM", "").split(",") if s.strip()]
IMESSAGE_SERVICE: str = os.getenv("IMESSAGE_SERVICE", "auto")

# Voice gateway (local microphone → STT → LLM → TTS → speaker)
VOICE_ENABLED: bool = os.getenv("VOICE_ENABLED", "false").lower() in ("true", "1", "yes")
WAKE_WORDS: list[str] = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "小圆, 小方").split(",") if w.strip()]
TTS_PROVIDER: str = os.getenv("TTS_PROVIDER", "volcengine")
TTS_VOICE: str = os.getenv("TTS_VOICE", "cedar")
TTS_MODEL: str = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_SPEED: float = float(os.getenv("TTS_SPEED", "1.2"))

# Volcengine TTS (火山引擎 / 豆包语音)
VOLCENGINE_TTS_API_KEY: str = os.getenv("VOLCENGINE_TTS_API_KEY", "")
VOLCENGINE_TTS_RESOURCE_ID: str = os.getenv("VOLCENGINE_TTS_RESOURCE_ID", "volc.service_type.10029")
VOLCENGINE_TTS_SPEAKER: str = os.getenv("VOLCENGINE_TTS_SPEAKER", "zh_male_beijingxiaoye_emo_v2_mars_bigtts")
STT_MODEL: str = os.getenv("STT_MODEL", "gpt-4o-transcribe")
STT_LANGUAGE: str = os.getenv("STT_LANGUAGE", "zh")
STT_PROMPT: str = os.getenv("STT_PROMPT", "") or f"This audio may contain these wake words: {', '.join(WAKE_WORDS)}"
VOICE_SILENCE_THRESHOLD: int = int(os.getenv("VOICE_SILENCE_THRESHOLD", "500"))
VOICE_SILENCE_DURATION: float = float(os.getenv("VOICE_SILENCE_DURATION", "1.5"))
VOICE_SAMPLE_RATE: int = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))

# DM whitelist — only these user IDs can DM the bot (empty = deny all DMs)
ALLOWED_DM_USERS: set[int] = {
    int(uid.strip()) for uid in os.getenv("ALLOWED_DM_USERS", "").split(",") if uid.strip()
}

# Auto-reply settings
AUTO_REPLY_ENABLED: bool = os.getenv("AUTO_REPLY_ENABLED", "false").lower() in ("true", "1", "yes")
AUTO_REPLY_CHANNELS: list[str] = os.getenv("AUTO_REPLY_CHANNELS", "").split(",")
AUTO_REPLY_CHANCE: float = float(os.getenv("AUTO_REPLY_CHANCE", "0.1"))
AUTO_REPLY_KEYWORDS: list[str] = os.getenv("AUTO_REPLY_KEYWORDS", "").split(",")

# Heartbeat settings
HEARTBEAT_ENABLED: bool = os.getenv("HEARTBEAT_ENABLED", "false").lower() in ("true", "1", "yes")
HEARTBEAT_INTERVAL: str = os.getenv("HEARTBEAT_INTERVAL", "30m")
HEARTBEAT_CHANNEL_ID: str = os.getenv("HEARTBEAT_CHANNEL_ID", "")
HEARTBEAT_ACTIVE_START: str = os.getenv("HEARTBEAT_ACTIVE_START", "")
HEARTBEAT_ACTIVE_END: str = os.getenv("HEARTBEAT_ACTIVE_END", "")
HEARTBEAT_ACTIVE_TZ: str = os.getenv("HEARTBEAT_ACTIVE_TZ", "")
HEARTBEAT_ACK_MAX_CHARS: int = int(os.getenv("HEARTBEAT_ACK_MAX_CHARS", "300"))
HEARTBEAT_ISOLATED: bool = os.getenv("HEARTBEAT_ISOLATED", "true").lower() in ("true", "1", "yes")
