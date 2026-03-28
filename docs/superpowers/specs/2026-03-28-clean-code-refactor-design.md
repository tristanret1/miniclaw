# MiniClaw Clean Code Refactor — Design Spec

**Date**: 2026-03-28
**Scope**: Pure refactoring, all features preserved
**Approach**: Phased incremental refactoring (4 phases)

---

## Constraints

- All existing features must be preserved
- Tests must pass after each phase (tests may be modified to match new structure)
- Coverage level is not enforced
- No new external dependencies beyond `pyyaml`

---

## 1. New Directory Structure

```
miniclaw/
├── config.yaml                      # Non-sensitive config (models, timeouts, thresholds)
├── .env                             # Sensitive only (tokens, passwords, API keys)
├── .env.example                     # Updated: only sensitive items
├── main.py
├── setup.py
│
├── bot/
│   ├── config.py                    # Load YAML + .env → AppConfig dataclass (lazy)
│   ├── client.py                    # Discord client (slim: event dispatch only)
│   ├── llm.py                       # Unified LLM entry point
│   ├── processor.py                 # Stream processor
│   ├── message.py                   # Message type definitions
│   ├── logger.py                    # Logging config
│   ├── constants.py                 # Global constants (Discord limits, protocol versions)
│   │
│   ├── config_schema/               # Config dataclass definitions
│   │   ├── __init__.py              # AppConfig (top-level, composes sub-configs)
│   │   ├── llm.py                   # LLMConfig, AnthropicConfig, CodexConfig
│   │   ├── discord.py               # DiscordConfig, AutoReplyConfig, StreamConfig
│   │   ├── gateway.py               # GatewayConfig, VoiceConfig, SMSConfig, etc.
│   │   ├── storage.py               # StorageConfig, SQLiteConfig
│   │   └── services.py              # ServicesConfig, TwilioConfig, GoogleConfig
│   │
│   ├── provider/                    # LLM providers (existing subpackage, enhanced)
│   │   ├── __init__.py              # Provider registry + get_provider()
│   │   ├── base.py                  # BaseProvider ABC + shared HTTPClientMixin
│   │   ├── anthropic.py             # Anthropic provider
│   │   ├── codex.py                 # Codex provider
│   │   └── transform.py            # Message sanitization
│   │
│   ├── tools/                       # Tool system (split from tools.py 965 LOC)
│   │   ├── __init__.py              # ALL_TOOLS registry + handle_tool_call() dispatcher
│   │   ├── exec.py                  # exec tool
│   │   ├── memory_tools.py          # memory_save / memory_search
│   │   ├── discord_send.py          # discord_send tool
│   │   ├── claude_code.py           # claude_code tool
│   │   ├── sms.py                   # sms_send / phone_call (delegates to services/twilio)
│   │   ├── calendar.py              # Google Calendar tool handlers
│   │   └── cron_tools.py            # cron_add / cron_list / cron_delete handlers
│   │
│   ├── gateway/                     # Gateways (consolidated from scattered files)
│   │   ├── __init__.py
│   │   ├── voice.py                 # VoiceGateway class (no global state)
│   │   ├── imessage.py              # iMessage gateway
│   │   ├── sms.py                   # SMS gateway
│   │   └── heartbeat.py             # Heartbeat scheduler
│   │
│   ├── storage/                     # Data storage layer
│   │   ├── __init__.py              # DB adapter (centralized use_postgres() logic)
│   │   ├── session.py               # SessionManager
│   │   ├── memory.py                # Memory storage + search
│   │   └── cron_db.py               # Cron job persistence
│   │
│   ├── services/                    # External service clients (deduplicated)
│   │   ├── __init__.py
│   │   ├── twilio.py                # TwilioClient (unified SMS + Voice)
│   │   └── google_calendar.py       # Google Calendar OAuth + API
│   │
│   ├── oauth/                       # Authentication (consolidated)
│   │   ├── __init__.py
│   │   ├── anthropic.py             # Anthropic OAuth PKCE
│   │   └── codex.py                 # Codex device auth
│   │
│   ├── utils/                       # Shared utilities
│   │   ├── __init__.py
│   │   ├── discord.py               # send_chunks(), message formatting
│   │   └── session_keys.py          # Unified session key generation
│   │
│   ├── agent.py                     # Multi-agent / persona
│   ├── acp.py                       # Claude Code integration
│   ├── commands.py                  # Discord slash commands
│   ├── cron.py                      # Cron scheduler (slim: scheduling only, DB in storage/)
│   ├── health.py                    # Health checks
│   └── skills.py                    # Skill loading
│
└── tests/                           # Tests follow new structure
    ├── conftest.py
    ├── test_message.py
    ├── test_processor.py
    ├── test_llm.py
    ├── test_client.py
    ├── provider/
    │   ├── test_transform.py
    │   ├── test_anthropic.py
    │   └── test_registry.py
    ├── tools/
    ├── gateway/
    ├── storage/
    └── services/
```

---

## 2. Configuration System

### 2.1 `config.yaml` — Non-Sensitive Configuration

```yaml
llm:
  provider: anthropic
  anthropic:
    model: claude-sonnet-4-20250514
    api_url: https://api.anthropic.com/v1/messages
  codex:
    model: gpt-5.3-codex
    api_url: https://chatgpt.com/backend-api/codex/responses
  max_history: 20
  max_tokens: 4096
  tools_enabled: true

discord:
  auto_reply:
    enabled: false
    channels: []
    chance: 0.1
    keywords: []
  stream:
    flush_interval: 0.1
    flush_chars: 50
  max_message_length: 2000

gateway:
  voice:
    enabled: false
    sample_rate: 16000
    silence_duration: 1.5
    conversation_timeout: 30.0
    playback_cooldown: 0.5
  sms:
    enabled: false
    max_message_length: 1600
  imessage:
    enabled: false
  heartbeat:
    enabled: false

storage:
  backend: sqlite
  sqlite:
    sessions_path: workspace/sessions.db
    memory_path: workspace/memory/memory.db

cron:
  tick_interval:
    min: 2.0
    max: 60.0
  backoff: [30, 60, 300, 900, 3600]

health:
  enabled: false

timeouts:
  http_read: 120
  http_connect: 10
  exec_default: 30
  exec_max: 120
  acp_max: 600
```

### 2.2 `.env` — Sensitive Items Only

```bash
DISCORD_BOT_TOKEN=
GITHUB_TOKEN=
OPENAI_API_KEY=
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
DATABASE_URL=
```

### 2.3 Config Loading (`config.py`)

- `load_config(path)` reads YAML + `.env`, returns `AppConfig` dataclass
- Lazy singleton via `get_config()` — no I/O at import time
- All dataclasses are `frozen=True` to prevent runtime mutation
- Every field has a sensible default; `config.yaml` only overrides what's needed

### 2.4 `constants.py` — Protocol/Platform Constants

Values that are not configurable (Discord API limits, protocol versions):

```python
DISCORD_MAX_MESSAGE_LENGTH = 2000
ANTHROPIC_API_VERSION = "2023-06-01"
MAX_TOOL_ROUNDS = 20
AUTO_FLUSH_CHAR_THRESHOLD = 80_000
MAX_FLUSH_ROUNDS = 5
```

---

## 3. Large File Split Strategy

### 3.1 `tools.py` (965 LOC) → `tools/` Subpackage

Each tool file exports:
- Tool schema dict (e.g., `EXEC_TOOL`)
- Async handler function (e.g., `run_exec()`)

`tools/__init__.py` collects all tools into `ALL_TOOLS` list and provides `handle_tool_call()` dispatcher via a `_HANDLERS` dict mapping tool name → handler function.

### 3.2 `cron.py` (692 LOC) Split

| Destination | Content | ~LOC |
|-------------|---------|------|
| `bot/cron.py` | CronScheduler: tick loop, job dispatch, backoff | ~200 |
| `bot/storage/cron_db.py` | Job persistence: add/list/delete/update_next_run | ~150 |
| `bot/tools/cron_tools.py` | cron_add/cron_list/cron_delete tool handlers | ~100 |

### 3.3 `voice_gateway.py` (421 LOC) → `gateway/voice.py`

Global mutable state (`_muted_until`, `_active_until`, `_engine`, `_agent`, `_announce_queue`) becomes instance attributes of `VoiceGateway` class. Testable, no hidden dependencies.

### 3.4 `memory.py` (468 LOC) → `storage/memory.py`

Stays as single file but:
- DB init and `use_postgres()` judgment centralized in `storage/__init__.py`
- Embedding call encapsulated as `_get_embedding(text) -> list[float]`
- Public API unchanged: `save()`, `search()`

### 3.5 `client.py` (354 LOC) Slimmed

Removed from client.py:
- `_known_users` dict → stays in client.py as private state (not global module var)
- `send_chunks()` → `utils/discord.py`
- Cron/heartbeat startup logic → respective modules manage own startup
- `GREETING_CHANNEL_ID` hardcode → `config.yaml`

client.py retains: event listeners, debounce, message dispatch to `llm.py`.

---

## 4. Duplicate Code Elimination

### 4.1 HTTP Client Base (`provider/base.py`)

Shared `_get_client() -> httpx.AsyncClient` method with configurable timeouts from `get_config().timeouts`. Both `anthropic.py` and `codex.py` inherit instead of duplicating.

### 4.2 Twilio Client (`services/twilio.py`)

`TwilioClient` class with `send_sms()` and `make_call()` methods. Replaces duplicate httpx + URL construction + auth handling in `tools.py`.

### 4.3 Discord Utilities (`utils/discord.py`)

`send_chunks(channel, text, chunk_size)` replaces 3+ identical implementations across client.py, cron.py, tools.py.

### 4.4 Session Keys (`utils/session_keys.py`)

Centralized functions for all 9 session key formats:
- `discord_key(channel_id, user_id)`
- `cron_key(job_id, isolated=False)`
- `voice_key()`
- `imessage_key(handle)`
- `sms_key(from_number)`
- `heartbeat_key(channel_id, isolated=False)`
- `greeting_key(channel_id)`

All modules call these functions instead of formatting strings inline.

---

## 5. Phased Implementation Plan

### Phase 1: Configuration System
1. Create `config.yaml` with all non-sensitive config
2. Create `config_schema/` with frozen dataclasses
3. Create `constants.py` for platform constants
4. Rewrite `config.py` with lazy `get_config()`
5. Slim `.env.example` to sensitive items only
6. Replace all `os.getenv()` calls and hardcoded values across all modules
7. **Gate: tests pass, bot starts normally**

### Phase 2: Module Split
1. `tools.py` → `tools/` subpackage (7 files)
2. Gateway files → `gateway/` subpackage
3. Storage files → `storage/` subpackage + centralized `use_postgres()` adapter
4. Auth files → `oauth/` subpackage
5. Create `services/twilio.py` + `services/google_calendar.py`
6. Create `utils/discord.py` + `utils/session_keys.py`
7. Update all import paths
8. **Gate: tests pass**

### Phase 3: Deduplication + State Cleanup
1. HTTP client extraction to `provider/base.py`
2. Twilio duplication → `TwilioClient`
3. Discord chunking → `utils/discord.py`
4. Session key calls → `utils/session_keys.py`
5. `voice_gateway` globals → `VoiceGateway` instance attributes
6. `client.py` globals cleanup, move cron/heartbeat startup out
7. **Gate: tests pass**

### Phase 4: Tests + Finalization
1. Restructure test files to match new directory layout
2. Fix import path changes in tests
3. Update `CLAUDE.md` project structure documentation
4. Update `pyproject.toml` pytest/coverage config
5. **Gate: all tests pass, bot runs normally**
