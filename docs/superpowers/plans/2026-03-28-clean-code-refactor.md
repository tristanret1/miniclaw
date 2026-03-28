# MiniClaw Clean Code Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor MiniClaw codebase for clean code: YAML config, subpackage structure, deduplicated code, unified constants — all features preserved.

**Architecture:** 4-phase incremental refactoring. Phase 1 migrates config from .env to YAML + dataclass. Phase 2 splits large files into subpackages (tools/, gateway/, storage/, services/, oauth/, utils/). Phase 3 deduplicates code and removes global mutable state. Phase 4 adjusts tests and documentation.

**Tech Stack:** Python 3.13+, PyYAML (new dependency), discord.py, httpx, SQLite/PostgreSQL, pytest

**Spec:** `docs/superpowers/specs/2026-03-28-clean-code-refactor-design.md`

---

## Phase 1: Configuration System

### Task 1: Add PyYAML dependency

**Files:**
- Modify: `requirements.txt`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pyyaml to requirements.txt**

Add `pyyaml>=6.0` to `requirements.txt`.

- [ ] **Step 2: Add pyyaml to pyproject.toml dependencies**

In `pyproject.toml` under `[project] dependencies`, add `"pyyaml>=6.0"`.

- [ ] **Step 3: Install updated dependencies**

Run: `pip install -e ".[dev]"`
Expected: Successfully installs pyyaml

- [ ] **Step 4: Commit**

```bash
git add requirements.txt pyproject.toml
git commit -m "chore: add pyyaml dependency for config migration"
```

---

### Task 2: Create constants.py

**Files:**
- Create: `bot/constants.py`

Collect all non-configurable magic numbers from across the codebase into one file. These are protocol/platform limits that should never be user-configurable.

- [ ] **Step 1: Create bot/constants.py**

```python
"""Non-configurable platform and protocol constants."""

# Discord
DISCORD_MAX_MESSAGE_LENGTH = 2000

# Anthropic API
ANTHROPIC_API_VERSION = "2023-06-01"
ANTHROPIC_BETA_FEATURES = (
    "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14"
)
CLAUDE_CODE_VERSION = "2.1.75"
CLAUDE_CODE_SYSTEM_PREFIX = (
    "You are Claude Code, Anthropic's official CLI for Claude."
)

# LLM processing
MAX_TOOL_ROUNDS = 20
MAX_FLUSH_ROUNDS = 5
AUTO_FLUSH_CHAR_THRESHOLD = 80_000  # ~20k tokens

# Tool output limits
TOOL_MAX_OUTPUT_CHARS = 4000
ACP_MAX_OUTPUT_CHARS = 8000

# Memory chunking
CHUNK_TOKENS = 400
CHUNK_OVERLAP = 80
CHARS_PER_TOKEN = 4

# Embedding
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
BM25_WEIGHT = 0.4
VECTOR_WEIGHT = 0.6

# OAuth
ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
ANTHROPIC_AUTH_URL = "https://claude.ai/oauth/authorize"
ANTHROPIC_TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
ANTHROPIC_REDIRECT_URI = "https://platform.claude.com/oauth/code/callback"
ANTHROPIC_SCOPES = (
    "org:create_api_key user:profile user:inference "
    "user:sessions:claude_code user:mcp_servers"
)

CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_ISSUER = "https://auth.openai.com"
CODEX_API_ENDPOINT = "https://chatgpt.com/backend-api/codex/responses"
CODEX_DEVICE_AUTH_PAGE = "https://auth.openai.com/codex/device"

# Skill loading
MAX_SKILL_FILE_BYTES = 256_000

# Heartbeat
HEARTBEAT_TOKEN = "HEARTBEAT_OK"

# Twilio
TWILIO_API_BASE = "https://api.twilio.com/2010-04-01/Accounts"

# OpenAI embeddings
OPENAI_EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"

# Google OAuth
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
```

- [ ] **Step 2: Verify import works**

Run: `python -c "from bot.constants import DISCORD_MAX_MESSAGE_LENGTH; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add bot/constants.py
git commit -m "refactor: create constants.py for non-configurable platform values"
```

---

### Task 3: Create config_schema/ dataclass package

**Files:**
- Create: `bot/config_schema/__init__.py`
- Create: `bot/config_schema/llm.py`
- Create: `bot/config_schema/discord.py`
- Create: `bot/config_schema/gateway.py`
- Create: `bot/config_schema/storage.py`
- Create: `bot/config_schema/services.py`

- [ ] **Step 1: Create bot/config_schema/llm.py**

```python
"""LLM provider configuration."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AnthropicProviderConfig:
    model: str = "claude-sonnet-4-20250514"
    api_url: str = "https://api.anthropic.com/v1/messages"


@dataclass(frozen=True)
class CodexProviderConfig:
    model: str = "gpt-5.3-codex"
    api_url: str = "https://chatgpt.com/backend-api/codex/responses"


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "anthropic"
    anthropic: AnthropicProviderConfig = field(
        default_factory=AnthropicProviderConfig
    )
    codex: CodexProviderConfig = field(default_factory=CodexProviderConfig)
    max_history: int = 50
    max_tokens: int = 4096
    tools_enabled: bool = False
```

- [ ] **Step 2: Create bot/config_schema/discord.py**

```python
"""Discord bot configuration."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class AutoReplyConfig:
    enabled: bool = False
    channels: list[str] = field(default_factory=list)
    chance: float = 0.1
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StreamConfig:
    flush_interval: float = 0.1
    flush_chars: int = 50


@dataclass(frozen=True)
class DiscordConfig:
    greeting_channel_id: str = ""
    allowed_dm_users: list[int] = field(default_factory=list)
    auto_reply: AutoReplyConfig = field(default_factory=AutoReplyConfig)
    stream: StreamConfig = field(default_factory=StreamConfig)
```

- [ ] **Step 3: Create bot/config_schema/gateway.py**

```python
"""Gateway configuration (voice, SMS, iMessage, heartbeat)."""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class VoiceConfig:
    enabled: bool = False
    sample_rate: int = 16000
    silence_threshold: int = 500
    silence_duration: float = 1.5
    conversation_timeout: float = 30.0
    playback_cooldown: float = 0.5
    wake_words: list[str] = field(default_factory=lambda: ["小圆", "小方"])
    tts_provider: str = "volcengine"
    tts_voice: str = "cedar"
    tts_model: str = "gpt-4o-mini-tts"
    tts_speed: float = 1.2
    stt_model: str = "gpt-4o-transcribe"
    stt_language: str = "zh"
    stt_prompt: str = ""


@dataclass(frozen=True)
class VolcengineConfig:
    tts_resource_id: str = "volc.service_type.10029"
    tts_speaker: str = "zh_male_beijingxiaoye_emo_v2_mars_bigtts"


@dataclass(frozen=True)
class SMSConfig:
    enabled: bool = False
    webhook_port: int = 8080
    webhook_url: str = ""
    max_message_length: int = 1600


@dataclass(frozen=True)
class IMessageConfig:
    enabled: bool = False
    cli_path: str = "imsg"
    db_path: str = ""
    allow_from: list[str] = field(default_factory=list)
    service: str = "auto"


@dataclass(frozen=True)
class HeartbeatConfig:
    enabled: bool = False
    interval: str = "30m"
    channel_id: str = ""
    active_start: str = ""
    active_end: str = ""
    active_tz: str = ""
    ack_max_chars: int = 300
    isolated: bool = True


@dataclass(frozen=True)
class GatewayConfig:
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    volcengine: VolcengineConfig = field(default_factory=VolcengineConfig)
    sms: SMSConfig = field(default_factory=SMSConfig)
    imessage: IMessageConfig = field(default_factory=IMessageConfig)
    heartbeat: HeartbeatConfig = field(default_factory=HeartbeatConfig)
```

- [ ] **Step 4: Create bot/config_schema/storage.py**

```python
"""Storage backend configuration."""
from dataclasses import dataclass


@dataclass(frozen=True)
class SQLiteConfig:
    sessions_path: str = "workspace/sessions.db"
    memory_path: str = "workspace/memory/memory.db"


@dataclass(frozen=True)
class StorageConfig:
    backend: str = "sqlite"
    sqlite: SQLiteConfig = None

    def __post_init__(self):
        if self.sqlite is None:
            object.__setattr__(self, "sqlite", SQLiteConfig())
```

- [ ] **Step 5: Create bot/config_schema/services.py**

```python
"""External services configuration."""
from dataclasses import dataclass


@dataclass(frozen=True)
class GoogleCalendarConfig:
    enabled: bool = False
    life_calendar_id: str = ""
    work_calendar_id: str = ""


@dataclass(frozen=True)
class CronConfig:
    enabled: bool = True
    timezone: str = "America/Vancouver"
    max_concurrent: int = 5
    tick_interval_min: float = 2.0
    tick_interval_max: float = 60.0
    backoff: tuple[int, ...] = (30, 60, 300, 900, 3600)


@dataclass(frozen=True)
class HealthConfig:
    enabled: bool = True


@dataclass(frozen=True)
class TimeoutConfig:
    http_read: int = 120
    http_connect: int = 10
    exec_default: int = 30
    exec_max: int = 120
    acp_max: int = 600


@dataclass(frozen=True)
class ServicesConfig:
    google_calendar: GoogleCalendarConfig = None
    cron: CronConfig = None
    health: HealthConfig = None
    timeouts: TimeoutConfig = None

    def __post_init__(self):
        for field_name, factory in [
            ("google_calendar", GoogleCalendarConfig),
            ("cron", CronConfig),
            ("health", HealthConfig),
            ("timeouts", TimeoutConfig),
        ]:
            if getattr(self, field_name) is None:
                object.__setattr__(self, field_name, factory())
```

- [ ] **Step 6: Create bot/config_schema/__init__.py**

```python
"""Application configuration — top-level dataclass composing all sub-configs."""
from dataclasses import dataclass, field, fields
from pathlib import Path

from bot.config_schema.llm import LLMConfig, AnthropicProviderConfig, CodexProviderConfig
from bot.config_schema.discord import DiscordConfig, AutoReplyConfig, StreamConfig
from bot.config_schema.gateway import (
    GatewayConfig, VoiceConfig, VolcengineConfig,
    SMSConfig, IMessageConfig, HeartbeatConfig,
)
from bot.config_schema.storage import StorageConfig, SQLiteConfig
from bot.config_schema.services import (
    ServicesConfig, GoogleCalendarConfig, CronConfig,
    HealthConfig, TimeoutConfig,
)

__all__ = [
    "AppConfig",
    "LLMConfig", "AnthropicProviderConfig", "CodexProviderConfig",
    "DiscordConfig", "AutoReplyConfig", "StreamConfig",
    "GatewayConfig", "VoiceConfig", "VolcengineConfig",
    "SMSConfig", "IMessageConfig", "HeartbeatConfig",
    "StorageConfig", "SQLiteConfig",
    "ServicesConfig", "GoogleCalendarConfig", "CronConfig",
    "HealthConfig", "TimeoutConfig",
]


def _build_dataclass(cls, raw: dict):
    """Recursively build a frozen dataclass from a nested dict."""
    if not isinstance(raw, dict):
        return raw
    kwargs = {}
    field_names = {f.name for f in fields(cls)}
    for key, value in raw.items():
        if key not in field_names:
            continue
        field_obj = next(f for f in fields(cls) if f.name == key)
        # If the field type is a dataclass, recurse
        origin = getattr(field_obj.type, "__origin__", None)
        if hasattr(field_obj.type, "__dataclass_fields__"):
            kwargs[key] = _build_dataclass(field_obj.type, value)
        elif origin is list and isinstance(value, list):
            kwargs[key] = value
        elif origin is tuple and isinstance(value, (list, tuple)):
            kwargs[key] = tuple(value)
        else:
            kwargs[key] = value
    return cls(**kwargs)


@dataclass(frozen=True)
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    services: ServicesConfig = field(default_factory=ServicesConfig)

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        """Build AppConfig from a parsed YAML dict."""
        return _build_dataclass(cls, raw)
```

- [ ] **Step 7: Verify all imports work**

Run: `python -c "from bot.config_schema import AppConfig; c = AppConfig(); print(c.llm.provider, c.services.timeouts.http_read)"`
Expected: `anthropic 120`

- [ ] **Step 8: Commit**

```bash
git add bot/config_schema/
git commit -m "refactor: create config_schema/ dataclass package for typed configuration"
```

---

### Task 4: Create config.yaml and rewrite config.py

**Files:**
- Create: `config.yaml`
- Modify: `bot/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Create config.yaml**

Create `config.yaml` at project root with all non-sensitive configuration values. Use the current `.env` defaults as source of truth. This file replaces the role of `.env` for non-secret values.

```yaml
llm:
  provider: anthropic
  anthropic:
    model: claude-sonnet-4-20250514
    api_url: https://api.anthropic.com/v1/messages
  codex:
    model: gpt-5.3-codex
    api_url: https://chatgpt.com/backend-api/codex/responses
  max_history: 50
  max_tokens: 4096
  tools_enabled: false

discord:
  greeting_channel_id: ""
  allowed_dm_users: []
  auto_reply:
    enabled: false
    channels: []
    chance: 0.1
    keywords: []
  stream:
    flush_interval: 0.1
    flush_chars: 50

gateway:
  voice:
    enabled: false
    sample_rate: 16000
    silence_threshold: 500
    silence_duration: 1.5
    conversation_timeout: 30.0
    playback_cooldown: 0.5
    wake_words:
      - "小圆"
      - "小方"
    tts_provider: volcengine
    tts_voice: cedar
    tts_model: gpt-4o-mini-tts
    tts_speed: 1.2
    stt_model: gpt-4o-transcribe
    stt_language: zh
    stt_prompt: ""
  volcengine:
    tts_resource_id: "volc.service_type.10029"
    tts_speaker: "zh_male_beijingxiaoye_emo_v2_mars_bigtts"
  sms:
    enabled: false
    webhook_port: 8080
    webhook_url: ""
    max_message_length: 1600
  imessage:
    enabled: false
    cli_path: imsg
    db_path: ""
    allow_from: []
    service: auto
  heartbeat:
    enabled: false
    interval: "30m"
    channel_id: ""
    active_start: ""
    active_end: ""
    active_tz: ""
    ack_max_chars: 300
    isolated: true

storage:
  backend: sqlite
  sqlite:
    sessions_path: workspace/sessions.db
    memory_path: workspace/memory/memory.db

services:
  google_calendar:
    enabled: false
    life_calendar_id: ""
    work_calendar_id: ""
  cron:
    enabled: true
    timezone: America/Vancouver
    max_concurrent: 5
    tick_interval_min: 2.0
    tick_interval_max: 60.0
    backoff: [30, 60, 300, 900, 3600]
  health:
    enabled: true
  timeouts:
    http_read: 120
    http_connect: 10
    exec_default: 30
    exec_max: 120
    acp_max: 600
```

- [ ] **Step 2: Rewrite bot/config.py**

Replace the current config.py entirely. The new version:
- Loads YAML config lazily via `get_config() -> AppConfig`
- Loads `.env` for sensitive values via `get_secrets() -> dict`
- Builds system prompt lazily via `get_system_prompt() -> str`
- Provides backward-compatible module-level constants as properties that read from the config singleton (temporary bridge — removed in Phase 2 when consumers migrate)

```python
"""Configuration loader — YAML for settings, .env for secrets."""
from __future__ import annotations

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

from bot.config_schema import AppConfig

PROJECT_ROOT = Path(__file__).parent.parent
WORKSPACE_DIR = PROJECT_ROOT / "workspace"
SKILLS_DIR = WORKSPACE_DIR / "skills"

_config: AppConfig | None = None
_system_prompt: str | None = None


def get_config(config_path: Path | None = None) -> AppConfig:
    """Return the global AppConfig singleton, loading from YAML on first call."""
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
    """Reset config singleton (for testing)."""
    global _config, _system_prompt
    _config = None
    _system_prompt = None


def get_secrets() -> dict[str, str]:
    """Load .env and return a dict of sensitive values."""
    load_dotenv(PROJECT_ROOT / ".env")
    return {
        "discord_bot_token": os.getenv("DISCORD_BOT_TOKEN", ""),
        "github_token": os.getenv("GITHUB_TOKEN", ""),
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "twilio_account_sid": os.getenv("TWILIO_ACCOUNT_SID", ""),
        "twilio_auth_token": os.getenv("TWILIO_AUTH_TOKEN", ""),
        "twilio_from_number": os.getenv("TWILIO_FROM_NUMBER", ""),
        "google_client_id": os.getenv("GOOGLE_CLIENT_ID", ""),
        "google_client_secret": os.getenv("GOOGLE_CLIENT_SECRET", ""),
        "database_url": os.getenv("DATABASE_URL", ""),
        "volcengine_tts_api_key": os.getenv("VOLCENGINE_TTS_API_KEY", ""),
        "acp_cwd": os.getenv("ACP_CWD", ""),
    }


def build_system_prompt(workspace_dir: Path | None = None) -> str:
    """Assemble system prompt from workspace Markdown files."""
    ws = workspace_dir or WORKSPACE_DIR
    parts: list[str] = []
    for name in ("SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"):
        path = ws / name
        if path.exists():
            text = path.read_text().strip()
            if text:
                parts.append(text)
    return "\n\n---\n\n".join(parts) if parts else "You are a helpful assistant."


def get_system_prompt(workspace_dir: Path | None = None) -> str:
    """Return cached system prompt, building on first call."""
    global _system_prompt
    if _system_prompt is None:
        _system_prompt = build_system_prompt(workspace_dir)
    return _system_prompt


def get_loaded_skills() -> list:
    """Load skills from workspace skills directory."""
    from bot.skills import load_skills
    return load_skills(SKILLS_DIR)


# ---------------------------------------------------------------------------
# Backward-compatible module-level names.
# These read from the YAML config / .env so existing code keeps working
# during the migration. They will be removed once all consumers switch to
# get_config() / get_secrets() directly.
# ---------------------------------------------------------------------------
load_dotenv(PROJECT_ROOT / ".env")

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")
PROVIDER = os.getenv("PROVIDER", "") or "anthropic"
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-20250514")
CODEX_MODEL = os.getenv("CODEX_MODEL", "gpt-5.3-codex")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "50"))
TOOLS_ENABLED = os.getenv("TOOLS_ENABLED", "false").lower() in ("1", "true", "yes")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")
ACP_CWD = os.getenv("ACP_CWD", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER", "")
HEALTH_TRACKING_ENABLED = os.getenv("HEALTH_TRACKING_ENABLED", "true").lower() in ("1", "true", "yes")
GOOGLE_CALENDAR_ENABLED = os.getenv("GOOGLE_CALENDAR_ENABLED", "false").lower() in ("1", "true", "yes")
GOOGLE_CALENDAR_CLIENT_ID = os.getenv("GOOGLE_CALENDAR_CLIENT_ID", "") or os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CALENDAR_CLIENT_SECRET = os.getenv("GOOGLE_CALENDAR_CLIENT_SECRET", "") or os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_CALENDAR_LIFE_ID = os.getenv("GOOGLE_CALENDAR_LIFE_ID", "")
GOOGLE_CALENDAR_WORK_ID = os.getenv("GOOGLE_CALENDAR_WORK_ID", "")
CRON_ENABLED = os.getenv("CRON_ENABLED", "true").lower() in ("1", "true", "yes")
CRON_TIMEZONE = os.getenv("CRON_TIMEZONE", "America/Vancouver")
CRON_MAX_CONCURRENT = int(os.getenv("CRON_MAX_CONCURRENT", "5"))
SMS_ENABLED = os.getenv("SMS_ENABLED", "false").lower() in ("1", "true", "yes")
SMS_WEBHOOK_PORT = int(os.getenv("SMS_WEBHOOK_PORT", "8080"))
SMS_WEBHOOK_URL = os.getenv("SMS_WEBHOOK_URL", "")
IMESSAGE_ENABLED = os.getenv("IMESSAGE_ENABLED", "false").lower() in ("1", "true", "yes")
IMESSAGE_CLI_PATH = os.getenv("IMESSAGE_CLI_PATH", "imsg")
IMESSAGE_DB_PATH = os.getenv("IMESSAGE_DB_PATH", "")
IMESSAGE_ALLOW_FROM = os.getenv("IMESSAGE_ALLOW_FROM", "")
IMESSAGE_SERVICE = os.getenv("IMESSAGE_SERVICE", "auto")
VOICE_ENABLED = os.getenv("VOICE_ENABLED", "false").lower() in ("1", "true", "yes")
WAKE_WORDS = os.getenv("WAKE_WORDS", "小圆, 小方")
TTS_PROVIDER = os.getenv("TTS_PROVIDER", "volcengine")
TTS_VOICE = os.getenv("TTS_VOICE", "cedar")
TTS_MODEL = os.getenv("TTS_MODEL", "gpt-4o-mini-tts")
TTS_SPEED = float(os.getenv("TTS_SPEED", "1.2"))
VOLCENGINE_TTS_API_KEY = os.getenv("VOLCENGINE_TTS_API_KEY", "")
VOLCENGINE_TTS_RESOURCE_ID = os.getenv("VOLCENGINE_TTS_RESOURCE_ID", "volc.service_type.10029")
VOLCENGINE_TTS_SPEAKER = os.getenv("VOLCENGINE_TTS_SPEAKER", "zh_male_beijingxiaoye_emo_v2_mars_bigtts")
STT_MODEL = os.getenv("STT_MODEL", "gpt-4o-transcribe")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "zh")
STT_PROMPT = os.getenv("STT_PROMPT", "") or WAKE_WORDS
VOICE_SILENCE_THRESHOLD = int(os.getenv("VOICE_SILENCE_THRESHOLD", "500"))
VOICE_SILENCE_DURATION = float(os.getenv("VOICE_SILENCE_DURATION", "1.5"))
VOICE_SAMPLE_RATE = int(os.getenv("VOICE_SAMPLE_RATE", "16000"))
ALLOWED_DM_USERS: set[int] = set()
_adm = os.getenv("ALLOWED_DM_USERS", "")
if _adm:
    ALLOWED_DM_USERS = {int(x.strip()) for x in _adm.split(",") if x.strip()}
AUTO_REPLY_ENABLED = os.getenv("AUTO_REPLY_ENABLED", "false").lower() in ("1", "true", "yes")
AUTO_REPLY_CHANNELS: set[int] = set()
_arc = os.getenv("AUTO_REPLY_CHANNELS", "")
if _arc:
    AUTO_REPLY_CHANNELS = {int(x.strip()) for x in _arc.split(",") if x.strip()}
AUTO_REPLY_CHANCE = float(os.getenv("AUTO_REPLY_CHANCE", "0.1"))
AUTO_REPLY_KEYWORDS: list[str] = []
_ark = os.getenv("AUTO_REPLY_KEYWORDS", "")
if _ark:
    AUTO_REPLY_KEYWORDS = [k.strip().lower() for k in _ark.split(",") if k.strip()]
HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "false").lower() in ("1", "true", "yes")
HEARTBEAT_INTERVAL = os.getenv("HEARTBEAT_INTERVAL", "30m")
HEARTBEAT_CHANNEL_ID = os.getenv("HEARTBEAT_CHANNEL_ID", "")
HEARTBEAT_ACTIVE_START = os.getenv("HEARTBEAT_ACTIVE_START", "")
HEARTBEAT_ACTIVE_END = os.getenv("HEARTBEAT_ACTIVE_END", "")
HEARTBEAT_ACTIVE_TZ = os.getenv("HEARTBEAT_ACTIVE_TZ", "")
HEARTBEAT_ACK_MAX_CHARS = int(os.getenv("HEARTBEAT_ACK_MAX_CHARS", "300"))
HEARTBEAT_ISOLATED = os.getenv("HEARTBEAT_ISOLATED", "true").lower() in ("1", "true", "yes")

SYSTEM_PROMPT = build_system_prompt()
```

- [ ] **Step 3: Update .env.example**

Replace the entire `.env.example` with only sensitive items and a comment pointing to `config.yaml`:

```bash
# MiniClaw Environment Variables
# Only secrets and credentials go here.
# All other settings are in config.yaml.

# === Required ===
DISCORD_BOT_TOKEN=

# === Optional: External Services ===
GITHUB_TOKEN=
OPENAI_API_KEY=
DATABASE_URL=

# === Optional: Twilio (SMS/Phone) ===
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# === Optional: Google Calendar ===
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=

# === Optional: Volcengine TTS ===
VOLCENGINE_TTS_API_KEY=

# === Optional: Claude Code ===
ACP_CWD=
```

- [ ] **Step 4: Run tests to verify nothing broke**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All existing tests pass (config.py still exports same module-level names)

- [ ] **Step 5: Commit**

```bash
git add config.yaml bot/config.py .env.example
git commit -m "refactor: add config.yaml + rewrite config.py with lazy loading and backward compat"
```

---

### Task 5: Migrate hardcoded values to constants.py across codebase

**Files:**
- Modify: `bot/provider/anthropic.py` — replace hardcoded API version, beta features, Claude Code strings
- Modify: `bot/processor.py` — replace `MAX_TOOL_ROUNDS = 20`
- Modify: `bot/memory.py` — replace `CHUNK_TOKENS`, `EMBEDDING_MODEL`, `BM25_WEIGHT`, etc.
- Modify: `bot/acp.py` — replace `MAX_OUTPUT_CHARS = 8000`
- Modify: `bot/tools.py` — replace `MAX_OUTPUT_CHARS = 4000`
- Modify: `bot/oauth.py` — replace OAuth constants
- Modify: `bot/codex_oauth.py` — replace OAuth constants
- Modify: `bot/heartbeat.py` — replace `HEARTBEAT_TOKEN`

- [ ] **Step 1: Update bot/provider/anthropic.py**

Replace hardcoded constants with imports from `bot.constants`:

```python
# At top of file, add:
from bot.constants import (
    ANTHROPIC_API_VERSION,
    ANTHROPIC_BETA_FEATURES,
    CLAUDE_CODE_VERSION,
    CLAUDE_CODE_SYSTEM_PREFIX,
)

# Remove the local definitions:
# _CLAUDE_CODE_VERSION = "2.1.75"  → delete
# _CLAUDE_CODE_SYSTEM_PREFIX = "..."  → delete
# Replace all usages of the local names with the imported constants
```

- [ ] **Step 2: Update bot/processor.py**

```python
# At top, add:
from bot.constants import MAX_TOOL_ROUNDS, MAX_FLUSH_ROUNDS

# Remove local: MAX_TOOL_ROUNDS = 20
# Use MAX_TOOL_ROUNDS and MAX_FLUSH_ROUNDS from constants
```

- [ ] **Step 3: Update bot/memory.py**

```python
# At top, add:
from bot.constants import (
    CHUNK_TOKENS, CHUNK_OVERLAP, CHARS_PER_TOKEN,
    EMBEDDING_MODEL, EMBEDDING_DIM,
    BM25_WEIGHT, VECTOR_WEIGHT,
    AUTO_FLUSH_CHAR_THRESHOLD,
    OPENAI_EMBEDDINGS_URL,
)

# Remove all local definitions of these constants
# Replace FLUSH_THRESHOLD_CHARS with AUTO_FLUSH_CHAR_THRESHOLD
```

- [ ] **Step 4: Update bot/acp.py**

```python
# At top, add:
from bot.constants import ACP_MAX_OUTPUT_CHARS

# Remove local: MAX_OUTPUT_CHARS = 8000
# Replace usage: MAX_OUTPUT_CHARS → ACP_MAX_OUTPUT_CHARS
```

- [ ] **Step 5: Update bot/tools.py**

```python
# At top, add:
from bot.constants import TOOL_MAX_OUTPUT_CHARS, TWILIO_API_BASE

# Remove local: MAX_OUTPUT_CHARS = 4000
# Replace: MAX_OUTPUT_CHARS → TOOL_MAX_OUTPUT_CHARS
# Replace hardcoded Twilio URL prefix with TWILIO_API_BASE
```

- [ ] **Step 6: Update bot/oauth.py**

```python
# At top, add:
from bot.constants import (
    ANTHROPIC_CLIENT_ID, ANTHROPIC_AUTH_URL,
    ANTHROPIC_TOKEN_URL, ANTHROPIC_REDIRECT_URI, ANTHROPIC_SCOPES,
)

# Remove local: CLIENT_ID, AUTHORIZATION_URL, TOKEN_URL, REDIRECT_URI, SCOPES
# Replace all usages with imported constants
```

- [ ] **Step 7: Update bot/codex_oauth.py**

```python
# At top, add:
from bot.constants import (
    CODEX_CLIENT_ID, CODEX_ISSUER, CODEX_API_ENDPOINT,
    CODEX_DEVICE_AUTH_PAGE,
)

# Remove local: CLIENT_ID, ISSUER, CODEX_API_ENDPOINT, DEVICE_AUTH_PAGE
# Derive remaining URLs from CODEX_ISSUER:
#   DEVICE_CODE_URL = f"{CODEX_ISSUER}/api/accounts/deviceauth/usercode"
#   DEVICE_TOKEN_URL = f"{CODEX_ISSUER}/api/accounts/deviceauth/token"
#   TOKEN_URL = f"{CODEX_ISSUER}/oauth/token"
```

- [ ] **Step 8: Update bot/heartbeat.py**

```python
# At top, add:
from bot.constants import HEARTBEAT_TOKEN

# Remove local: HEARTBEAT_TOKEN = "HEARTBEAT_OK"
```

- [ ] **Step 9: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 10: Commit**

```bash
git add bot/constants.py bot/provider/anthropic.py bot/processor.py bot/memory.py bot/acp.py bot/tools.py bot/oauth.py bot/codex_oauth.py bot/heartbeat.py
git commit -m "refactor: migrate hardcoded values to constants.py across all modules"
```

---

## Phase 2: Module Split

### Task 6: Create utils/ package

**Files:**
- Create: `bot/utils/__init__.py`
- Create: `bot/utils/discord.py`
- Create: `bot/utils/session_keys.py`

- [ ] **Step 1: Create bot/utils/__init__.py**

```python
"""Shared utility functions."""
```

- [ ] **Step 2: Create bot/utils/discord.py**

Extract the Discord message chunking logic that is duplicated in client.py, cron.py, and tools.py:

```python
"""Discord message utilities."""
from bot.constants import DISCORD_MAX_MESSAGE_LENGTH


async def send_chunks(
    channel,
    text: str,
    chunk_size: int = DISCORD_MAX_MESSAGE_LENGTH,
) -> None:
    """Send a long message as multiple chunks to a Discord channel."""
    for i in range(0, len(text), chunk_size):
        await channel.send(text[i : i + chunk_size])
```

- [ ] **Step 3: Create bot/utils/session_keys.py**

Centralize all session key formats:

```python
"""Centralized session key generation.

All modules must use these functions instead of formatting keys inline.
Format: "{namespace}:{identifier}" with optional ":timestamp" for isolated sessions.
"""
import time


def discord_key(channel_id: int, user_id: int) -> str:
    return f"{channel_id}:{user_id}"


def greeting_key(channel_id: int | str) -> str:
    return f"{channel_id}:system"


def cron_key(job_id: str, *, isolated: bool = False) -> str:
    if isolated:
        return f"cron:{job_id}:{int(time.time())}"
    return f"cron:{job_id}"


def heartbeat_key(channel_id: str, *, isolated: bool = False) -> str:
    if isolated:
        return f"{channel_id}:heartbeat:{int(time.time())}"
    return f"{channel_id}:heartbeat"


def voice_key() -> str:
    return "voice:local"


def imessage_key(handle: str) -> str:
    """Normalize iMessage handle and create session key."""
    normalized = handle.strip().lower().lstrip("+")
    return f"imessage:{normalized}"


def sms_key(from_number: str) -> str:
    return f"sms:{from_number}"
```

- [ ] **Step 4: Verify imports**

Run: `python -c "from bot.utils.discord import send_chunks; from bot.utils.session_keys import discord_key; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add bot/utils/
git commit -m "refactor: create utils/ package with discord helpers and session key functions"
```

---

### Task 7: Create tools/ subpackage

**Files:**
- Create: `bot/tools/__init__.py`
- Create: `bot/tools/exec.py`
- Create: `bot/tools/memory_tools.py`
- Create: `bot/tools/discord_send.py`
- Create: `bot/tools/claude_code.py`
- Create: `bot/tools/sms.py`
- Create: `bot/tools/calendar.py`
- Create: `bot/tools/cron_tools.py`
- Create: `bot/tools/health_tools.py`
- Create: `bot/tools/voice_tools.py`
- Create: `bot/tools/imessage_tools.py`
- Delete: `bot/tools.py` (after migration)

This is the largest split. Read the current `bot/tools.py` carefully and extract each tool's schema dict + handler function into its own file. The `__init__.py` re-exports `ALL_TOOLS` and `handle_tool_call()`.

- [ ] **Step 1: Read current bot/tools.py to identify exact tool boundaries**

Read the full file to identify each tool schema and its handler function, including line ranges.

- [ ] **Step 2: Create bot/tools/exec.py**

Extract `EXEC_TOOL` schema dict and `run_exec()` handler. The handler uses `asyncio.create_subprocess_shell` with configurable timeout and workdir. Import `TOOL_MAX_OUTPUT_CHARS` from constants and `GITHUB_TOKEN` from config.

- [ ] **Step 3: Create bot/tools/memory_tools.py**

Extract `MEMORY_SAVE_TOOL`, `MEMORY_SEARCH_TOOL` schemas and their handler logic. The handlers delegate to `bot.memory.save()` and `bot.memory.search()`.

- [ ] **Step 4: Create bot/tools/discord_send.py**

Extract `DISCORD_SEND_TOOL` schema and `run_discord_send()`. Uses lazy import of `bot.client.bot` to avoid circular dependency.

- [ ] **Step 5: Create bot/tools/claude_code.py**

Extract `CLAUDE_CODE_TOOL` schema and handler that delegates to `bot.acp.run_prompt()`.

- [ ] **Step 6: Create bot/tools/sms.py**

Extract `SMS_TOOL`, `PHONE_CALL_TOOL` schemas and `run_sms()`, `run_phone_call()` handlers. Keep the Twilio HTTP logic here for now (Phase 3 will extract TwilioClient).

- [ ] **Step 7: Create bot/tools/calendar.py**

Extract `GOOGLE_CALENDAR_TOOL` schema and `run_google_calendar()` handler.

- [ ] **Step 8: Create bot/tools/cron_tools.py**

Extract `CRON_CREATE_TOOL`, `CRON_LIST_TOOL`, `CRON_DELETE_TOOL` schemas and handlers that delegate to `bot.cron.create_job()`, `list_jobs()`, `delete_job()`.

- [ ] **Step 9: Create bot/tools/health_tools.py**

Extract `HEALTH_LOG_TOOL`, `HEALTH_STATS_TOOL`, `HEALTH_GOAL_TOOL` schemas and handlers that delegate to `bot.health.*`.

- [ ] **Step 10: Create bot/tools/voice_tools.py**

Extract `VOICE_ANNOUNCE_TOOL` schema and handler that delegates to `bot.voice_gateway.announce()`.

- [ ] **Step 11: Create bot/tools/imessage_tools.py**

Extract `IMESSAGE_SEND_TOOL` schema and handler.

- [ ] **Step 12: Create bot/tools/__init__.py**

```python
"""Tool system — registry and dispatcher."""
from bot.tools.exec import EXEC_TOOL, run_exec
from bot.tools.memory_tools import (
    MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL,
    run_memory_save, run_memory_search,
)
from bot.tools.discord_send import DISCORD_SEND_TOOL, run_discord_send
from bot.tools.claude_code import CLAUDE_CODE_TOOL, run_claude_code
from bot.tools.sms import SMS_TOOL, PHONE_CALL_TOOL, run_sms, run_phone_call
from bot.tools.calendar import GOOGLE_CALENDAR_TOOL, run_google_calendar
from bot.tools.cron_tools import (
    CRON_CREATE_TOOL, CRON_LIST_TOOL, CRON_DELETE_TOOL,
    run_cron_create, run_cron_list, run_cron_delete,
)
from bot.tools.health_tools import (
    HEALTH_LOG_TOOL, HEALTH_STATS_TOOL, HEALTH_GOAL_TOOL,
    run_health_log, run_health_stats, run_health_goal,
)
from bot.tools.voice_tools import VOICE_ANNOUNCE_TOOL, run_voice_announce
from bot.tools.imessage_tools import IMESSAGE_SEND_TOOL, run_imessage_send
from bot.config import (
    VOICE_ENABLED, GOOGLE_CALENDAR_ENABLED, HEALTH_TRACKING_ENABLED,
)

_BASE_TOOLS = [
    EXEC_TOOL,
    MEMORY_SAVE_TOOL,
    MEMORY_SEARCH_TOOL,
    CLAUDE_CODE_TOOL,
    DISCORD_SEND_TOOL,
    CRON_CREATE_TOOL,
    CRON_LIST_TOOL,
    CRON_DELETE_TOOL,
    PHONE_CALL_TOOL,
    SMS_TOOL,
    IMESSAGE_SEND_TOOL,
]

ALL_TOOLS: list[dict] = list(_BASE_TOOLS)
if VOICE_ENABLED:
    ALL_TOOLS.append(VOICE_ANNOUNCE_TOOL)
if GOOGLE_CALENDAR_ENABLED:
    ALL_TOOLS.append(GOOGLE_CALENDAR_TOOL)
if HEALTH_TRACKING_ENABLED:
    ALL_TOOLS.extend([HEALTH_LOG_TOOL, HEALTH_STATS_TOOL, HEALTH_GOAL_TOOL])

_HANDLERS: dict[str, object] = {
    "exec": run_exec,
    "memory_save": run_memory_save,
    "memory_search": run_memory_search,
    "claude_code": run_claude_code,
    "discord_send": run_discord_send,
    "cron_create": run_cron_create,
    "cron_list": run_cron_list,
    "cron_delete": run_cron_delete,
    "sms_send": run_sms,
    "phone_call": run_phone_call,
    "imessage_send": run_imessage_send,
    "voice_announce": run_voice_announce,
    "google_calendar": run_google_calendar,
    "health_log": run_health_log,
    "health_stats": run_health_stats,
    "health_goal": run_health_goal,
}


async def handle_tool_call(
    tool_name: str,
    tool_input: dict,
    memory_dir=None,
    agent_name: str = "",
) -> str:
    """Dispatch a tool call to the appropriate handler."""
    handler = _HANDLERS.get(tool_name)
    if handler is None:
        return f"Unknown tool: {tool_name}"
    # Some handlers accept memory_dir/agent_name, some don't.
    # Use try/except for simplicity during migration.
    import inspect
    sig = inspect.signature(handler)
    kwargs = dict(tool_input)
    if "memory_dir" in sig.parameters:
        kwargs["memory_dir"] = memory_dir
    if "agent_name" in sig.parameters:
        kwargs["agent_name"] = agent_name
    return await handler(**kwargs)
```

Note: The exact handler function signatures and tool names must match the current `tools.py` implementation. Read the actual file to get the precise names.

- [ ] **Step 13: Update all imports of bot.tools across the codebase**

Search for `from bot.tools import` and `import bot.tools` in all files and update to `from bot.tools import ALL_TOOLS, handle_tool_call` (the __init__.py re-exports everything).

Key files to update:
- `bot/processor.py`
- `bot/llm.py`
- `bot/cron.py`
- Any test files referencing `bot.tools`

- [ ] **Step 14: Delete old bot/tools.py**

After verifying all imports work, remove the original monolithic file.

- [ ] **Step 15: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 16: Commit**

```bash
git add bot/tools/ bot/processor.py bot/llm.py bot/cron.py
git rm bot/tools.py
git commit -m "refactor: split tools.py (965 LOC) into tools/ subpackage with per-tool modules"
```

---

### Task 8: Create gateway/ subpackage

**Files:**
- Create: `bot/gateway/__init__.py`
- Move: `bot/voice_gateway.py` → `bot/gateway/voice.py`
- Move: `bot/imessage_gateway.py` → `bot/gateway/imessage.py`
- Move: `bot/sms_gateway.py` → `bot/gateway/sms.py`
- Move: `bot/heartbeat.py` → `bot/gateway/heartbeat.py`

- [ ] **Step 1: Create bot/gateway/__init__.py**

```python
"""Gateway modules for non-Discord communication channels."""
```

- [ ] **Step 2: Move voice_gateway.py → gateway/voice.py**

```bash
git mv bot/voice_gateway.py bot/gateway/voice.py
```

- [ ] **Step 3: Move imessage_gateway.py → gateway/imessage.py**

```bash
git mv bot/imessage_gateway.py bot/gateway/imessage.py
```

- [ ] **Step 4: Move sms_gateway.py → gateway/sms.py**

```bash
git mv bot/sms_gateway.py bot/gateway/sms.py
```

- [ ] **Step 5: Move heartbeat.py → gateway/heartbeat.py**

```bash
git mv bot/heartbeat.py bot/gateway/heartbeat.py
```

- [ ] **Step 6: Update all imports across codebase**

Search and replace:
- `from bot.voice_gateway import` → `from bot.gateway.voice import`
- `from bot.imessage_gateway import` → `from bot.gateway.imessage import`
- `from bot.sms_gateway import` → `from bot.gateway.sms import`
- `from bot.heartbeat import` → `from bot.gateway.heartbeat import`
- `import bot.voice_gateway` → `import bot.gateway.voice`

Key files to update: `main.py`, `bot/client.py`, `bot/tools/voice_tools.py`, `bot/tools/imessage_tools.py`, all gateway test files.

- [ ] **Step 7: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add bot/gateway/ main.py bot/client.py bot/tools/
git commit -m "refactor: consolidate gateways into gateway/ subpackage"
```

---

### Task 9: Create storage/ subpackage

**Files:**
- Create: `bot/storage/__init__.py`
- Move: `bot/session.py` → `bot/storage/session.py`
- Move: `bot/memory.py` → `bot/storage/memory.py`
- Extract cron DB logic from `bot/cron.py` → `bot/storage/cron_db.py`
- Move: `bot/db.py` → `bot/storage/db.py` (the postgres adapter)

- [ ] **Step 1: Create bot/storage/__init__.py**

```python
"""Data storage layer — SQLite/PostgreSQL adapters, session, memory, cron persistence."""
from bot.storage.db import use_postgres, get_pool, ensure_schema

__all__ = ["use_postgres", "get_pool", "ensure_schema"]
```

- [ ] **Step 2: Move db.py → storage/db.py**

```bash
git mv bot/db.py bot/storage/db.py
```

- [ ] **Step 3: Move session.py → storage/session.py**

```bash
git mv bot/session.py bot/storage/session.py
```

- [ ] **Step 4: Move memory.py → storage/memory.py**

```bash
git mv bot/memory.py bot/storage/memory.py
```

- [ ] **Step 5: Extract cron DB operations to storage/cron_db.py**

Read `bot/cron.py` and extract all SQLite/PostgreSQL database operations (table creation, CRUD for cron_jobs) into `bot/storage/cron_db.py`. The scheduler logic stays in `bot/cron.py`. The cron_db module exports functions like:
- `init_db()` — create table
- `load_jobs()` → list of CronJob dicts
- `insert_job()`, `delete_job()`, `update_job()`
- `CronJob` dataclass stays in cron.py (it's a domain object)

- [ ] **Step 6: Update all imports across codebase**

Search and replace:
- `from bot.session import` → `from bot.storage.session import`
- `from bot.memory import` → `from bot.storage.memory import`
- `from bot.db import` → `from bot.storage.db import` (or `from bot.storage import`)
- `import bot.session` → `import bot.storage.session`

Key files to update: `bot/llm.py`, `bot/processor.py`, `bot/tools/memory_tools.py`, `bot/cron.py`, `main.py`, `bot/agent.py`, all related test files.

- [ ] **Step 7: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add bot/storage/ bot/cron.py bot/llm.py bot/processor.py bot/tools/ main.py bot/agent.py
git rm bot/session.py bot/memory.py bot/db.py
git commit -m "refactor: create storage/ subpackage for session, memory, and cron persistence"
```

---

### Task 10: Create oauth/ subpackage

**Files:**
- Create: `bot/oauth/__init__.py`
- Move: `bot/oauth.py` → `bot/oauth/anthropic.py`
- Move: `bot/codex_oauth.py` → `bot/oauth/codex.py`

- [ ] **Step 1: Create bot/oauth/ directory and __init__.py**

```python
"""OAuth authentication for LLM providers."""
from bot.oauth.anthropic import (
    authorize as authorize_anthropic,
    load_credentials as load_anthropic_credentials,
    refresh_token as refresh_anthropic_token,
    save_credentials as save_anthropic_credentials,
    CREDENTIALS_PATH as ANTHROPIC_CREDENTIALS_PATH,
)
from bot.oauth.codex import (
    authorize_headless as authorize_codex,
    load_credentials as load_codex_credentials,
    refresh_token as refresh_codex_token,
    save_credentials as save_codex_credentials,
    CREDENTIALS_PATH as CODEX_CREDENTIALS_PATH,
)
```

- [ ] **Step 2: Move oauth.py → oauth/anthropic.py**

```bash
mkdir -p bot/oauth
git mv bot/oauth.py bot/oauth/anthropic.py
```

- [ ] **Step 3: Move codex_oauth.py → oauth/codex.py**

```bash
git mv bot/codex_oauth.py bot/oauth/codex.py
```

- [ ] **Step 4: Update all imports**

Search and replace:
- `from bot.oauth import` → `from bot.oauth.anthropic import` (or `from bot.oauth import`)
- `from bot.codex_oauth import` → `from bot.oauth.codex import` (or `from bot.oauth import`)

Key files: `bot/provider/anthropic.py`, `bot/provider/codex.py`, `setup.py`, test files.

- [ ] **Step 5: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add bot/oauth/
git commit -m "refactor: consolidate OAuth modules into oauth/ subpackage"
```

---

### Task 11: Create services/ subpackage

**Files:**
- Create: `bot/services/__init__.py`
- Create: `bot/services/twilio.py`
- Move: `bot/google_calendar.py` → `bot/services/google_calendar.py`

- [ ] **Step 1: Create bot/services/__init__.py**

```python
"""External service clients."""
```

- [ ] **Step 2: Create bot/services/twilio.py**

Extract the duplicated Twilio HTTP logic from `bot/tools/sms.py` into a reusable client:

```python
"""Twilio API client for SMS and voice calls."""
import httpx

from bot.constants import TWILIO_API_BASE
from bot.config import get_secrets


class TwilioClient:
    """Unified Twilio client for SMS and voice calls."""

    def __init__(
        self,
        account_sid: str = "",
        auth_token: str = "",
        from_number: str = "",
    ):
        secrets = get_secrets() if not account_sid else {}
        self._sid = account_sid or secrets.get("twilio_account_sid", "")
        self._token = auth_token or secrets.get("twilio_auth_token", "")
        self._from = from_number or secrets.get("twilio_from_number", "")

    def _check_configured(self) -> str | None:
        """Return error message if Twilio is not configured, else None."""
        if not all([self._sid, self._token, self._from]):
            return "Twilio credentials not configured."
        return None

    async def send_sms(self, to: str, body: str) -> dict:
        err = self._check_configured()
        if err:
            return {"error": err}
        url = f"{TWILIO_API_BASE}/{self._sid}/Messages.json"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                auth=(self._sid, self._token),
                data={"To": to, "From": self._from, "Body": body},
            )
            return resp.json()

    async def make_call(self, to: str, twiml: str) -> dict:
        err = self._check_configured()
        if err:
            return {"error": err}
        url = f"{TWILIO_API_BASE}/{self._sid}/Calls.json"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                url,
                auth=(self._sid, self._token),
                data={"To": to, "From": self._from, "Twiml": twiml},
            )
            return resp.json()
```

- [ ] **Step 3: Move google_calendar.py → services/google_calendar.py**

```bash
git mv bot/google_calendar.py bot/services/google_calendar.py
```

- [ ] **Step 4: Update imports**

- `from bot.google_calendar import` → `from bot.services.google_calendar import`
- Update `bot/tools/calendar.py` and `bot/tools/sms.py` to use the new paths
- Update `bot/tools/sms.py` to use `TwilioClient` instead of inline httpx calls

- [ ] **Step 5: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add bot/services/ bot/tools/sms.py bot/tools/calendar.py
git rm bot/google_calendar.py
git commit -m "refactor: create services/ subpackage with TwilioClient and Google Calendar"
```

---

## Phase 3: Deduplication + State Cleanup

### Task 12: Extract HTTP client to provider base class

**Files:**
- Modify: `bot/provider/base.py`
- Modify: `bot/provider/anthropic.py`
- Modify: `bot/provider/codex.py`

- [ ] **Step 1: Add shared HTTP client to base.py**

```python
"""LLM provider base class with shared HTTP client management."""
from abc import ABC, abstractmethod
from typing import AsyncIterator

import httpx

from bot.config import get_config


class BaseProvider(ABC):
    _http: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        """Return a shared httpx client, creating one if needed."""
        if self._http is None or self._http.is_closed:
            cfg = get_config().services.timeouts
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(cfg.http_read, connect=cfg.http_connect),
                http2=True,
                limits=httpx.Limits(
                    max_connections=10, max_keepalive_connections=5
                ),
            )
        return self._http

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http and not self._http.is_closed:
            await self._http.aclose()
            self._http = None

    @abstractmethod
    async def stream(self, messages, system, tools=None, max_tokens=4096) -> AsyncIterator[dict]:
        ...

    @abstractmethod
    async def call(self, messages, system, tools=None, max_tokens=4096) -> dict:
        ...

    @abstractmethod
    async def refresh_auth(self) -> None:
        ...
```

- [ ] **Step 2: Remove duplicate _get_client() from anthropic.py**

Remove the local `_get_client()` method and the local `httpx.Timeout(120, connect=10)` hardcoded values. The provider now inherits `_get_client()` from `BaseProvider`.

- [ ] **Step 3: Remove duplicate _get_client() from codex.py**

Same treatment as anthropic.py.

- [ ] **Step 4: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add bot/provider/base.py bot/provider/anthropic.py bot/provider/codex.py
git commit -m "refactor: extract shared HTTP client to BaseProvider, remove duplication"
```

---

### Task 13: Replace inline Discord chunking with utils

**Files:**
- Modify: `bot/client.py`
- Modify: `bot/cron.py`
- Modify: `bot/tools/discord_send.py`

- [ ] **Step 1: Update bot/client.py**

Find all occurrences of the chunking pattern:
```python
chunks = [text[i : i + 2000] for i in range(0, len(text), 2000)]
for chunk in chunks:
    await channel.send(chunk)
```
Replace with:
```python
from bot.utils.discord import send_chunks
await send_chunks(channel, text)
```

- [ ] **Step 2: Update bot/cron.py**

Same replacement for chunking logic in cron job result delivery.

- [ ] **Step 3: Update bot/tools/discord_send.py**

Same replacement in the discord_send tool handler.

- [ ] **Step 4: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add bot/client.py bot/cron.py bot/tools/discord_send.py
git commit -m "refactor: replace 3 inline Discord chunking patterns with utils.send_chunks()"
```

---

### Task 14: Replace inline session keys with utils

**Files:**
- Modify: `bot/client.py`
- Modify: `bot/cron.py`
- Modify: `bot/gateway/voice.py`
- Modify: `bot/gateway/imessage.py`
- Modify: `bot/gateway/sms.py`
- Modify: `bot/gateway/heartbeat.py`

- [ ] **Step 1: Update bot/client.py**

Replace:
- `f"{GREETING_CHANNEL_ID}:system"` → `from bot.utils.session_keys import greeting_key; greeting_key(GREETING_CHANNEL_ID)`
- `f"{message.channel.id}:{message.author.id}"` → `from bot.utils.session_keys import discord_key; discord_key(message.channel.id, message.author.id)`

- [ ] **Step 2: Update bot/cron.py**

Replace:
- `f"cron:{job.id}"` → `from bot.utils.session_keys import cron_key; cron_key(job.id)`
- `f"cron:{job.id}:{int(time.time())}"` → `cron_key(job.id, isolated=True)`

- [ ] **Step 3: Update bot/gateway/voice.py**

Replace:
- `SESSION_KEY = "voice:local"` → `from bot.utils.session_keys import voice_key; SESSION_KEY = voice_key()`

- [ ] **Step 4: Update bot/gateway/imessage.py**

Replace inline key formatting with `imessage_key()`.

- [ ] **Step 5: Update bot/gateway/sms.py**

Replace inline key formatting with `sms_key()`.

- [ ] **Step 6: Update bot/gateway/heartbeat.py**

Replace inline key formatting with `heartbeat_key()`.

- [ ] **Step 7: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 8: Commit**

```bash
git add bot/client.py bot/cron.py bot/gateway/
git commit -m "refactor: centralize all session key generation via utils.session_keys"
```

---

### Task 15: Encapsulate voice gateway global state

**Files:**
- Modify: `bot/gateway/voice.py`

- [ ] **Step 1: Wrap globals into VoiceGateway class**

Read `bot/gateway/voice.py` and convert the module-level globals into instance attributes of a `VoiceGateway` class:

```python
class VoiceGateway:
    def __init__(self, agent: Agent | None = None):
        self._muted_until: float = 0.0
        self._active_until: float = 0.0
        self._engine: AudioEngine | None = None
        self._agent = agent
        self._announce_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        self._playback_cooldown = get_config().gateway.voice.playback_cooldown
        self._conversation_timeout = get_config().gateway.voice.conversation_timeout

    async def start(self) -> None:
        """Start the voice gateway (replaces module-level start_voice_gateway)."""
        ...

    async def announce(self, message: str, source: str = "") -> str:
        """Push an announcement to the voice queue."""
        ...
```

- [ ] **Step 2: Update module-level functions to delegate to singleton**

Keep backward-compatible `start_voice_gateway()` and `announce()` module functions that create/use a module-level `VoiceGateway` instance. This avoids changing all callers at once.

```python
_gateway: VoiceGateway | None = None

async def start_voice_gateway(agent: Agent | None = None) -> None:
    global _gateway
    _gateway = VoiceGateway(agent)
    await _gateway.start()

async def announce(message: str, source: str = "") -> str:
    if _gateway is None:
        return "Voice gateway not started"
    return await _gateway.announce(message, source)
```

- [ ] **Step 3: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add bot/gateway/voice.py
git commit -m "refactor: encapsulate voice gateway global state into VoiceGateway class"
```

---

### Task 16: Clean up client.py globals

**Files:**
- Modify: `bot/client.py`

- [ ] **Step 1: Move GREETING_CHANNEL_ID to config**

Remove the hardcoded `GREETING_CHANNEL_ID = 1482258781860532344` and read it from `get_config().discord.greeting_channel_id` instead.

- [ ] **Step 2: Remove cron/heartbeat startup coupling**

Move the cron and heartbeat startup logic out of `client.py`'s `on_ready` handler. Instead, have `main.py` orchestrate startup by calling cron/heartbeat start functions after the bot is ready.

Read the current `on_ready` to see exactly how cron/heartbeat startup is triggered, then refactor so `client.py` emits a callback or `main.py` handles it directly.

- [ ] **Step 3: Run tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add bot/client.py main.py
git commit -m "refactor: clean up client.py globals, move cron/heartbeat startup to main.py"
```

---

## Phase 4: Tests + Finalization

### Task 17: Restructure test files

**Files:**
- Create: `tests/tools/` directory with test files
- Create: `tests/gateway/` directory with test files
- Create: `tests/storage/` directory with test files
- Create: `tests/services/` directory with test files
- Move existing test files to match new structure

- [ ] **Step 1: Create test subdirectories**

```bash
mkdir -p tests/tools tests/gateway tests/storage tests/services tests/oauth
```

- [ ] **Step 2: Move tool tests**

```bash
git mv tests/test_tools.py tests/tools/test_tools.py
```

- [ ] **Step 3: Move gateway tests**

```bash
git mv tests/test_voice_gateway.py tests/gateway/test_voice.py
git mv tests/test_heartbeat.py tests/gateway/test_heartbeat.py
git mv tests/test_imessage_gateway.py tests/gateway/test_imessage.py
git mv tests/test_sms_gateway.py tests/gateway/test_sms.py
git mv tests/test_wake.py tests/gateway/test_wake.py
git mv tests/test_tts.py tests/gateway/test_tts.py
git mv tests/test_stt.py tests/gateway/test_stt.py
```

- [ ] **Step 4: Move storage tests**

```bash
git mv tests/test_session.py tests/storage/test_session.py
git mv tests/test_memory.py tests/storage/test_memory.py
git mv tests/test_cron.py tests/storage/test_cron.py
```

- [ ] **Step 5: Move service tests**

```bash
git mv tests/test_google_calendar.py tests/services/test_google_calendar.py
git mv tests/test_health.py tests/services/test_health.py
```

- [ ] **Step 6: Move OAuth tests**

```bash
git mv tests/test_oauth.py tests/oauth/test_oauth.py
```

If there is a test_codex_integration.py:
```bash
git mv tests/test_codex_integration.py tests/oauth/test_codex_integration.py
```

- [ ] **Step 7: Add __init__.py to each test subdirectory**

Create empty `__init__.py` in `tests/tools/`, `tests/gateway/`, `tests/storage/`, `tests/services/`, `tests/oauth/`.

- [ ] **Step 8: Fix all import paths in moved test files**

Update imports in each moved test file:
- `from bot.tools import` → `from bot.tools import` (unchanged, the package interface is stable)
- `from bot.voice_gateway import` → `from bot.gateway.voice import`
- `from bot.session import` → `from bot.storage.session import`
- `from bot.memory import` → `from bot.storage.memory import`
- `from bot.heartbeat import` → `from bot.gateway.heartbeat import`
- `from bot.google_calendar import` → `from bot.services.google_calendar import`
- etc.

- [ ] **Step 9: Update conftest.py if needed**

Check if `tests/conftest.py` references any moved modules and update paths.

- [ ] **Step 10: Run all tests**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -x -q`
Expected: All tests pass

- [ ] **Step 11: Commit**

```bash
git add tests/
git commit -m "refactor: restructure tests to match new module layout"
```

---

### Task 18: Update documentation and project config

**Files:**
- Modify: `CLAUDE.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Update CLAUDE.md project structure**

Replace the `## Project Structure` section with the new directory layout. Update the architecture diagram. Update the configuration section to document `config.yaml` instead of `.env` for non-sensitive config.

- [ ] **Step 2: Update pyproject.toml**

Update pytest configuration if test paths changed:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

Ensure coverage config includes new subpackages:
```toml
[tool.coverage.run]
source = ["bot"]
```

- [ ] **Step 3: Run final test suite**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -v`
Expected: All tests pass with new paths shown

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md pyproject.toml
git commit -m "docs: update CLAUDE.md and pyproject.toml for new project structure"
```

---

### Task 19: Final verification

- [ ] **Step 1: Verify bot starts**

Run: `cd /Users/sen/side_project/miniclaw && python -c "from bot.config import get_config; c = get_config(); print(f'Provider: {c.llm.provider}, Model: {c.llm.anthropic.model}')"`
Expected: `Provider: anthropic, Model: claude-sonnet-4-20250514`

- [ ] **Step 2: Verify all imports resolve**

Run: `python -c "from bot.tools import ALL_TOOLS, handle_tool_call; from bot.gateway.voice import start_voice_gateway; from bot.storage.session import SessionManager; from bot.oauth.anthropic import load_credentials; from bot.services.twilio import TwilioClient; from bot.utils.session_keys import discord_key; print(f'{len(ALL_TOOLS)} tools loaded, all imports OK')"`
Expected: `N tools loaded, all imports OK`

- [ ] **Step 3: Run full test suite**

Run: `cd /Users/sen/side_project/miniclaw && python -m pytest -v --tb=short`
Expected: All tests pass

- [ ] **Step 4: Check for stale files**

Run: `cd /Users/sen/side_project/miniclaw && git status`
Verify no orphaned `.py` files left in `bot/` that should have been moved.

- [ ] **Step 5: Final commit if needed**

Clean up any remaining issues found during verification.
