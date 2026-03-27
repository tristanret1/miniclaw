import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CODEX_MODEL = os.getenv("CODEX_MODEL", "gpt-5.3-codex")
PROVIDER = os.getenv("PROVIDER", "anthropic")  # "anthropic" or "codex"
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "200"))
TOOLS_ENABLED = os.getenv("TOOLS_ENABLED", "false").lower() in ("true", "1", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")  # for embedding (text-embedding-3-small)

# PostgreSQL (Neon) — when set, all storage uses PostgreSQL instead of SQLite
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Claude Code integration (via claude-agent-sdk)
ACP_CWD = os.getenv("ACP_CWD", "")  # default working directory for Claude Code tasks

# GitHub token for gh CLI and git push
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# Twilio (for phone_call tool)
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")  # E.164 format, e.g. +14155551234

WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"
SKILLS_DIR = Path(__file__).parent.parent / "skills"

# Bootstrap files injected into system prompt, same order as openclaw
_BOOTSTRAP_FILES = ["SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]


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


def get_loaded_skills():
    """Return loaded skills (cached after first system prompt build)."""
    from bot.skills import load_skills
    return load_skills(SKILLS_DIR)


SYSTEM_PROMPT = build_system_prompt()

# Health tracking
HEALTH_TRACKING_ENABLED = os.getenv("HEALTH_TRACKING_ENABLED", "true").lower() in ("true", "1", "yes")

# Google Calendar integration
GOOGLE_CALENDAR_ENABLED = os.getenv("GOOGLE_CALENDAR_ENABLED", "false").lower() in ("true", "1", "yes")
GOOGLE_CALENDAR_CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "")
GOOGLE_CALENDAR_LIFE_ID = os.getenv("GOOGLE_CALENDAR_LIFE_ID", "")  # personal calendar ID
GOOGLE_CALENDAR_WORK_ID = os.getenv("GOOGLE_CALENDAR_WORK_ID", "")  # work calendar ID (read-only)

# Cron scheduler
CRON_ENABLED = os.getenv("CRON_ENABLED", "true").lower() in ("true", "1", "yes")
CRON_TIMEZONE = os.getenv("CRON_TIMEZONE", "America/Vancouver")
CRON_MAX_CONCURRENT = int(os.getenv("CRON_MAX_CONCURRENT", "5"))

# SMS gateway (Twilio inbound webhook)
SMS_ENABLED = os.getenv("SMS_ENABLED", "false").lower() in ("true", "1", "yes")
SMS_WEBHOOK_PORT = int(os.getenv("SMS_WEBHOOK_PORT", "8080"))
SMS_WEBHOOK_URL = os.getenv("SMS_WEBHOOK_URL", "")  # public URL for Twilio signature validation

# iMessage gateway (via imsg CLI)
IMESSAGE_ENABLED = os.getenv("IMESSAGE_ENABLED", "false").lower() in ("true", "1", "yes")
IMESSAGE_CLI_PATH = os.getenv("IMESSAGE_CLI_PATH", "imsg")  # path to imsg binary
IMESSAGE_DB_PATH = os.getenv("IMESSAGE_DB_PATH", "")  # path to Messages/chat.db (optional)
IMESSAGE_ALLOW_FROM = [s.strip() for s in os.getenv("IMESSAGE_ALLOW_FROM", "").split(",") if s.strip()]
IMESSAGE_SERVICE = os.getenv("IMESSAGE_SERVICE", "auto")  # "imessage", "sms", or "auto"

# Voice gateway (local microphone → STT → LLM → TTS → speaker)
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() in ("true", "1", "yes")
WAKE_WORDS = [w.strip().lower() for w in os.getenv("WAKE_WORDS", "小圆, 小方").split(",") if w.strip()]
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "volcengine")  # "volcengine", "openai", or "edge"
TTS_VOICE = os.getenv("TTS_VOICE", "cedar")  # OpenAI voice name
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")  # OpenAI TTS model
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.2"))  # speech speed (0.25-4.0, default 1.2)

# Volcengine TTS (火山引擎 / 豆包语音)
VOLCENGINE_TTS_API_KEY = os.getenv("VOLCENGINE_TTS_API_KEY", "")
VOLCENGINE_TTS_RESOURCE_ID = os.getenv("VOLCENGINE_TTS_RESOURCE_ID", "volc.service_type.10029")
VOLCENGINE_TTS_SPEAKER = os.getenv("VOLCENGINE_TTS_SPEAKER", "zh_male_beijingxiaoye_emo_v2_mars_bigtts")
STT_MODEL = os.getenv("STT_MODEL", "gpt-4o-transcribe")  # OpenAI STT model
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "zh")  # language hint for STT
STT_PROMPT = os.getenv("STT_PROMPT", "") or f"This audio may contain these wake words: {', '.join(WAKE_WORDS)}"
VOICE_SILENCE_THRESHOLD = int(os.getenv("VOICE_SILENCE_THRESHOLD", "500"))  # RMS threshold
VOICE_SILENCE_DURATION = float(os.getenv("VOICE_SILENCE_DURATION", "1.5"))  # seconds of silence to segment
VOICE_SAMPLE_RATE = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))  # Hz

# DM whitelist — only these user IDs can DM the bot (empty = deny all DMs)
ALLOWED_DM_USERS: set[int] = {
    int(uid.strip()) for uid in os.getenv("ALLOWED_DM_USERS", "").split(",") if uid.strip()
}

# Auto-reply settings
AUTO_REPLY_ENABLED = os.getenv("AUTO_REPLY_ENABLED", "false").lower() in ("true", "1", "yes")
AUTO_REPLY_CHANNELS = os.getenv("AUTO_REPLY_CHANNELS", "").split(",")  # Channel IDs where auto-reply is allowed
AUTO_REPLY_CHANCE = float(os.getenv("AUTO_REPLY_CHANCE", "0.1"))  # 0.1 = 10% chance to reply
AUTO_REPLY_KEYWORDS = os.getenv("AUTO_REPLY_KEYWORDS", "").split(",")  # Keywords that trigger auto-reply

# Heartbeat settings
HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "false").lower() in ("true", "1", "yes")
HEARTBEAT_INTERVAL = os.getenv("HEARTBEAT_INTERVAL", "30m")  # e.g. "30m", "1h", "2h30m"
HEARTBEAT_CHANNEL_ID = os.getenv("HEARTBEAT_CHANNEL_ID", "")  # Discord channel for heartbeat delivery
HEARTBEAT_ACTIVE_START = os.getenv("HEARTBEAT_ACTIVE_START", "")  # "HH:MM" (24h), inclusive
HEARTBEAT_ACTIVE_END = os.getenv("HEARTBEAT_ACTIVE_END", "")  # "HH:MM" (24h), exclusive
HEARTBEAT_ACTIVE_TZ = os.getenv("HEARTBEAT_ACTIVE_TZ", "")  # IANA timezone (empty = local)
HEARTBEAT_ACK_MAX_CHARS = int(os.getenv("HEARTBEAT_ACK_MAX_CHARS", "300"))
HEARTBEAT_ISOLATED = os.getenv("HEARTBEAT_ISOLATED", "true").lower() in ("true", "1", "yes")
