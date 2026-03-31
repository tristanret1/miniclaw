# MiniClaw — System Design Document

- Repo: minimal Discord chatbot powered by Claude / Codex (multi-provider)
- Language: Python 3.13+
- No build step; pytest for testing.

---

## Project Structure

```
miniclaw/
├── main.py                          # Entry point
├── setup.py                         # Interactive first-time setup (OAuth + Discord token)
├── pyproject.toml                   # Project metadata, pytest config, coverage settings
├── requirements.txt                 # Runtime dependencies
├── config.yaml                      # Non-sensitive config (models, features, timeouts)
├── .env                             # Secrets only (tokens, API keys — gitignored)
├── .env.example                     # Secrets template
├── .credentials.json                # Anthropic OAuth tokens (gitignored, 0o600 perms)
├── .codex_credentials.json          # Codex OAuth tokens (gitignored, 0o600 perms)
│
├── bot/                             # Core application modules
│   ├── config.py                    # Config loader: config.yaml + .env → AppConfig singleton
│   ├── config_schema.py             # Frozen dataclass definitions for AppConfig
│   ├── constants.py                 # Non-configurable platform/protocol constants
│   ├── client.py                    # Discord client, event handlers, streaming display
│   ├── llm.py                       # Unified LLM entry point: stream() / reply()
│   ├── processor.py                 # Stream processor: tool loop, content accumulation, auto-flush
│   ├── message.py                   # Unified message types (Message, Content, ContentBlock)
│   ├── acp.py                       # Claude Code integration (claude-agent-sdk)
│   ├── commands.py                  # Discord slash commands (/autoreply)
│   ├── logger.py                    # Logging config (stdout + rotating file)
│   ├── agent.py                     # Agent loop helpers
│   ├── skills.py                    # Bot skill registry
│   ├── cron.py                      # Cron job scheduler
│   ├── health.py                    # Health tracking
│   ├── stt.py                       # Speech-to-text (OpenAI Whisper)
│   ├── tts.py                       # Text-to-speech (OpenAI / Volcengine)
│   ├── wake.py                      # Wake word detection
│   ├── audio_engine.py              # Audio I/O engine (AVAudioEngine / PyAudio)
│   ├── hooks.py                     # Agent lifecycle hook registry
│   ├── google_oauth.py              # Google OAuth 2.0 flow
│   │
│   ├── provider/                    # LLM provider abstraction layer
│   │   ├── __init__.py              # Provider registry + get_provider() factory
│   │   ├── base.py                  # BaseProvider ABC (stream, call, refresh_auth)
│   │   ├── anthropic.py             # Anthropic: OAuth, httpx, SSE streaming
│   │   ├── codex.py                 # Codex: OpenAI Responses API, OAuth, SSE streaming
│   │   └── transform.py             # Message sanitization middleware per provider
│   │
│   ├── tools/                       # Tool definitions + execution handlers
│   │   ├── __init__.py              # ALL_TOOLS registry + handle_tool_call() dispatch
│   │   ├── exec.py                  # Shell command execution
│   │   ├── memory_tools.py          # memory_save / memory_search tools
│   │   ├── claude_code.py           # claude_code tool (ACP delegation)
│   │   ├── discord_send.py          # discord_send tool
│   │   ├── calendar.py              # Google Calendar tools
│   │   ├── cron_tools.py            # Cron job management tools
│   │   ├── health_tools.py          # Health tracking tools
│   │   ├── imessage_tools.py        # iMessage send/read tools
│   │   ├── sms.py                   # SMS tools (Twilio)
│   │   └── voice_tools.py           # Voice control tools
│   │
│   ├── gateway/                     # Non-Discord inbound/outbound gateways
│   │   ├── __init__.py
│   │   ├── api.py                   # HTTP/WS API gateway for external consumers
│   │   ├── voice.py                 # Voice: mic → STT → wake → LLM → TTS → speaker
│   │   ├── imessage.py              # iMessage gateway (imsg CLI via JSON-RPC)
│   │   ├── sms.py                   # Twilio SMS inbound webhook (aiohttp)
│   │   └── heartbeat.py             # Periodic agent polling (default-silent)
│   │
│   ├── storage/                     # Persistence layer
│   │   ├── __init__.py
│   │   ├── db.py                    # DB backend factory (PostgreSQL / SQLite)
│   │   ├── session.py               # Session management: in-memory cache + DB persistence
│   │   └── memory.py                # SQLite + FTS5/BM25 + optional vector hybrid search
│   │
│   ├── oauth/                       # OAuth credential management
│   │   ├── __init__.py
│   │   ├── anthropic.py             # Anthropic PKCE flow, credential save/load/refresh
│   │   └── codex.py                 # Codex device auth flow, token refresh
│   │
│   ├── services/                    # External service clients
│   │   ├── __init__.py
│   │   ├── google_calendar.py       # Google Calendar API wrapper
│   │   └── twilio.py                # Twilio SMS/voice client
│   │
│   └── utils/                       # Shared utilities
│       ├── __init__.py
│       ├── discord.py               # Discord message chunking helpers
│       └── session_keys.py          # Centralized session key generation
│
├── workspace/                       # Bot personality + persistent data
│   ├── SOUL.md                      # Behavior principles, language preferences
│   ├── IDENTITY.md                  # Agent name, emoji, vibe
│   ├── memory/                      # Memory database + daily Markdown logs (gitignored)
│   │   ├── memory.db                # SQLite + FTS5 memory database
│   │   └── YYYY-MM-DD.md            # Daily memory logs (human-readable)
│   └── sessions.db                  # Conversation history (gitignored)
│
└── tests/                           # pytest test suite
    ├── conftest.py                  # Shared fixtures (FakeProvider, temp DBs, fake credentials)
    ├── test_message.py              # message.py tests
    ├── test_processor.py            # processor.py tests
    ├── test_llm.py                  # llm.py tests
    ├── test_client.py               # client.py tests
    ├── provider/
    │   ├── test_transform.py        # transform.py tests
    │   ├── test_anthropic.py        # anthropic.py tests
    │   ├── test_codex.py            # codex.py tests
    │   └── test_registry.py         # provider registry tests
    ├── storage/
    │   ├── test_session.py          # session.py tests
    │   ├── test_memory.py           # memory.py tests
    │   └── test_cron.py             # cron.py tests
    ├── gateway/
    │   ├── test_voice.py            # voice.py tests
    │   ├── test_imessage.py         # imessage.py tests
    │   ├── test_sms.py              # sms.py tests
    │   ├── test_heartbeat.py        # heartbeat.py tests
    │   ├── test_stt.py              # stt.py tests
    │   ├── test_tts.py              # tts.py tests
    │   └── test_wake.py             # wake.py tests
    ├── oauth/
    │   └── test_oauth.py            # oauth/ tests
    ├── services/
    │   ├── test_google_calendar.py  # google_calendar.py tests
    │   ├── test_health.py           # health.py tests
    │   └── test_skills.py           # skills.py tests
    └── tools/
        └── test_tools.py            # tools/ tests
```

---

## Architecture Overview

```
                          Discord
                            │
                  ┌─────────▼──────────┐
                  │   client.py        │  on_message / on_message_edit
                  │  ┌──────────────┐  │
                  │  │  debounce    │  │  1.5s wait for edits
                  │  │  1.5s timer  │  │
                  │  └──────┬───────┘  │
                  │         │          │
                  │  _process_message  │  extract text + images → build_user_content
                  │         │          │
                  └─────────┼──────────┘
                            │
                  ┌─────────▼──────────┐
                  │     llm.py         │  Unified entry: stream() / reply()
                  │  ┌──────────────┐  │
                  │  │ Singletons:  │  │  _provider (AnthropicProvider)
                  │  │  provider    │  │  _session_mgr (SessionManager)
                  │  │  session_mgr │  │
                  │  └──────┬───────┘  │
                  └─────────┼──────────┘
                            │
                  ┌─────────▼──────────┐
                  │  processor.py      │  StreamProcessor
                  │                    │
                  │  1. session.append(user_content)
                  │  2. check auto-flush
                  │  3. tool loop (max 20 rounds):
                  │  │  ├─ provider.stream(history)
                  │  │  ├─ accumulate content blocks
                  │  │  ├─ yield text chunks → Discord
                  │  │  ├─ if stop_reason == "tool_use":
                  │  │  │   ├─ handle_tool_call() concurrently
                  │  │  │   ├─ session.append(tool_results)
                  │  │  │   └─ continue loop
                  │  │  └─ else: done
                  │  4. session.append(assistant_content)
                  └────────────────────┘
                            │
              ┌─────────────┼─────────────┐
              │             │             │
    ┌─────────▼───┐  ┌─────▼──────────┐  ┌───▼──────────┐
    │ provider/   │  │ storage/       │  │  tools/      │
    │ anthropic   │  │ session.py     │  │              │
    │  .py        │  │                │  │ exec         │
    │             │  │ SessionMgr     │  │ memory_save  │
    │ HTTP POST   │  │  ┌──────┐      │  │ memory_search│
    │ SSE parse   │  │  │cache │      │  │ claude_code  │
    │ 401 refresh │  │  │ dict │      │  │ discord_send │
    └─────────────┘  │  └──┬───┘      │  └──────────────┘
                     │     │          │
                     │  ┌──▼───┐      │
                     │  │SQLite│      │  workspace/sessions.db
                     │  └──────┘      │
                     └────────────────┘
```

---

## Core Workflows

### 1. Startup Flow

```
main.py
  │
  ├─ Check .env + .credentials.json exist → if not, run setup.py
  │
  ├─ import bot.config
  │   ├─ load_dotenv() → read .env (secrets)
  │   ├─ AppConfig.load("config.yaml") → frozen dataclass (config_schema.py)
  │   │   └─ Merges YAML defaults with env overrides where applicable
  │   ├─ WORKSPACE_DIR = project_root / "workspace"
  │   └─ SYSTEM_PROMPT = build_system_prompt()
  │       ├─ Read workspace/SOUL.md
  │       ├─ Read workspace/IDENTITY.md
  │       └─ Join with "---" separator; fallback: "You are a helpful assistant."
  │
  ├─ import bot.client → creates discord.Client with message_content intent
  │
  └─ asyncio.run(bot.start(DISCORD_BOT_TOKEN))
      └─ on_ready → print "MiniClaw online as {bot.user}"
```

### 2. Message Handling Flow (DM / @mention)

```
on_message(message)
  │
  ├─ Skip if message.author == bot.user (self)
  │
  ├─ _remember_user(message)                    # Save user profile to memory
  │   └─ memory.save() if user is new or name changed
  │
  ├─ Check should_auto_reply(message)           # Random auto-reply in guilds
  │   ├─ AUTO_REPLY_ENABLED?
  │   ├─ Channel in AUTO_REPLY_CHANNELS?
  │   ├─ Keyword match in AUTO_REPLY_KEYWORDS?
  │   └─ random() < AUTO_REPLY_CHANCE?
  │   If yes → llm.reply() non-streaming → send reply → return
  │
  ├─ _should_handle(message)
  │   ├─ DM → always handle
  │   └─ Guild → only if bot.user in message.mentions
  │
  └─ Debounce (1.5s):
      ├─ Cancel any pending task for this message.id
      ├─ Create _debounced_reply(message) task
      └─ on_message_edit → cancel + restart debounce timer
          │
          └─ After 1.5s with no edits:
              _process_message(message)
                │
                ├─ _extract_content(message)       # Strip <@bot_id> mentions
                ├─ _extract_image_urls(message)    # Attachments + embeds
                │   └─ Filter by MIME: png, jpeg, gif, webp
                │
                ├─ session_key = "{channel_id}:{author_id}"
                │
                ├─ build_user_content(text, image_urls)
                │   ├─ Text only → return str
                │   └─ With images → return [ImageBlock..., TextBlock]
                │
                └─ llm.reply(session_key, user_content) → non-streaming
                    └─ Send reply split at 2000 chars
```

### 3. LLM Call Flow (Streaming)

```
llm.stream(session_key, user_content)
  │
  ├─ Get/create singleton: _provider (AnthropicProvider)
  ├─ Get/create singleton: _session_mgr (SessionManager)
  │
  └─ StreamProcessor(provider, session, session_key).process(user_content)
      │
      ├─ session.append(session_key, "user", user_content)    # Cache + DB
      ├─ session.trim(session_key)                            # Keep ≤ MAX_HISTORY*2
      │
      ├─ Auto-flush check:
      │   └─ If total history chars > 80,000 (~20k tokens) AND not already flushed:
      │       └─ asyncio.create_task(_run_flush(...))          # Background task
      │           └─ Append flush prompt to history copy
      │           └─ provider.call() → tool loop (up to 5 rounds)
      │           └─ Claude calls memory_save to persist key facts
      │
      ├─ history = session.get_history(session_key)
      │   └─ First access: load from SQLite → sanitize → cache
      │
      └─ Tool Loop (max 20 rounds):
          │
          ├─ provider.stream(history, SYSTEM_PROMPT, tools=ALL_TOOLS)
          │   │
          │   │  AnthropicProvider.stream():
          │   ├─ token = load_credentials()["access_token"]
          │   ├─ POST https://api.anthropic.com/v1/messages
          │   │   Headers: Bearer {token}, anthropic-version, anthropic-beta
          │   │   Body: {model, max_tokens:4096, system, messages, stream:true, tools}
          │   │
          │   └─ Parse SSE stream line by line:
          │       "event: content_block_start"  → init new content block
          │       "event: content_block_delta"  → accumulate text/tool_input
          │       "event: content_block_stop"   → finalize tool_use input (JSON parse)
          │       "event: message_delta"        → extract stop_reason
          │
          ├─ For each text_delta: yield chunk → client displays progressively
          │
          ├─ On complete: session.append("assistant", collected_content)
          │
          ├─ If stop_reason != "tool_use": return (done)
          │
          └─ If stop_reason == "tool_use":
              ├─ Extract tool_use blocks from collected_content
              ├─ Execute concurrently: asyncio.gather(*[handle_tool_call(...)])
              ├─ Build tool_result blocks
              ├─ session.append("user", tool_results)
              └─ Continue loop → re-call provider with updated history

      Error recovery:
        ├─ "Auth expired" during stream → fallback to provider.call() (non-streaming)
        └─ 400/tool mismatch → sanitize(history) → retry
```

### 4. Provider Call (Non-Streaming)

**Anthropic:**
```
AnthropicProvider.call(messages, system, tools, max_tokens)
  │
  ├─ token = load_credentials()["access_token"]
  ├─ body = {model, max_tokens, system, messages, stream:false, tools}
  ├─ POST https://api.anthropic.com/v1/messages
  │
  ├─ If 401:
  │   ├─ creds = load_credentials()
  │   ├─ new_creds = refresh_token(creds)      # POST /v1/oauth/token
  │   │   └─ save_credentials(new_creds)        # .credentials.json (0o600)
  │   └─ Retry POST with new access_token
  │
  ├─ If non-200: raise RuntimeError
  │
  └─ Return response JSON
```

**Codex:**
```
CodexProvider.call(messages, system, tools, max_tokens)
  │
  ├─ creds = _get_auth()                  # Auto-refresh if expired
  ├─ body = {model, input: [...], max_output_tokens, stream:false, tools}
  │   ├─ _to_codex_messages():            # Convert message format
  │   │   user text → {role: "user", content: [{type: "input_text", text}]}
  │   │   assistant → {role: "assistant", content: [{type: "output_text", text}]}
  │   │   tool_use  → {type: "function_call", call_id, name, arguments}
  │   │   tool_result → {type: "function_call_output", call_id, output}
  │   │   system    → {role: "developer", content: str}
  │   └─ _to_codex_tools():              # Convert tool definitions
  │       Anthropic {name, input_schema} → OpenAI {type:"function", name, parameters}
  │
  ├─ POST https://chatgpt.com/backend-api/codex/responses
  │   Headers: Bearer {token}, ChatGPT-Account-Id (for org subscriptions)
  │
  ├─ _codex_response_to_anthropic():      # Convert response back
  │   message/output_text → {type: "text", text}
  │   function_call       → {type: "tool_use", id, name, input}
  │
  └─ Return Anthropic-compatible response dict
```

---

## Session History Management

### Storage Architecture

```
SessionManager
  │
  ├─ _cache: dict[str, list[Message]]    # In-memory: keyed by "{channel_id}:{user_id}"
  └─ _flushed: set[str]                  # Track which sessions have been flushed

  workspace/sessions.db (SQLite, WAL mode)
    Table: messages
      ├─ id          INTEGER PRIMARY KEY AUTOINCREMENT
      ├─ session_key TEXT NOT NULL         # "{channel_id}:{user_id}"
      ├─ role        TEXT NOT NULL         # "user" or "assistant"
      ├─ content     TEXT NOT NULL         # JSON string or plain text
      └─ created_at  TEXT NOT NULL DEFAULT datetime('now')
    Index: idx_messages_session ON (session_key, id)
```

### Lifecycle

1. **First access** (`get_history`): Load from DB (most recent `MAX_HISTORY * 2` messages) → sanitize → cache
2. **Append** (`append`): Add to cache list + INSERT into DB (write-through)
3. **Trim** (`trim`): If cache exceeds `MAX_HISTORY * 2`, truncate + re-sanitize
4. **Clear** (`clear`): Delete from both cache and DB
5. **Restart**: Cache is lost; next `get_history` reloads from DB

### Message Sanitization (`provider/transform.py`)

Runs on every DB load and on 400 error recovery. Anthropic API constraints:

| Rule | Action |
|------|--------|
| `tool_use` block without matching `tool_result` | Drop the pair |
| `tool_result` without preceding `tool_use` | Drop the message |
| Mismatched `tool_use_id` / `tool_use_id` | Drop the pair |
| History starts with `assistant` | Remove leading assistant messages |
| Consecutive same-role messages | Drop duplicates to enforce alternation |

### Auto-Flush

When total history exceeds ~80,000 chars (~20k tokens):

1. Background task created (doesn't block reply)
2. Copy current history + append flush prompt
3. Call Claude with tool access — Claude calls `memory_save` to persist key facts
4. Up to 5 tool rounds, then mark session as flushed (won't trigger again)

---

## Tool System

### Available Tools

| Tool | Description | Key Parameters |
|------|-------------|----------------|
| `exec` | Execute shell command on host | `command`, `timeout` (max 120s), `workdir` |
| `memory_save` | Save to long-term memory (SQLite + Markdown) | `content`, `tags[]` |
| `memory_search` | Hybrid search (BM25 + optional vector) | `query`, `max_results` |
| `claude_code` | Delegate to Claude Code agent (ACP) | `task`, `cwd`, `timeout` (max 600s) |
| `discord_send` | Send message to Discord channel (disabled) | `channel_id`, `message` |

### Tool Execution Flow

```
processor._handle_tool_calls(tool_blocks)
  │
  ├─ For each tool_use block, concurrently (asyncio.gather):
  │   └─ handle_tool_call(name, input)
  │       ├─ "exec"          → run_exec(command, timeout, workdir)
  │       │                     └─ asyncio.create_subprocess_shell
  │       │                     └─ Inject GITHUB_TOKEN into env
  │       │                     └─ Truncate output at 4000 chars
  │       │
  │       ├─ "memory_save"   → memory.save(content, tags)
  │       │                     └─ INSERT into SQLite memories table
  │       │                     └─ Generate embedding (if OPENAI_API_KEY set)
  │       │                     └─ Append to daily Markdown log
  │       │
  │       ├─ "memory_search" → memory.search(query, max_results)
  │       │                     └─ FTS5 BM25 keyword search
  │       │                     └─ Optional: OpenAI embedding → cosine similarity
  │       │                     └─ Weighted merge (BM25=0.4, vector=0.6)
  │       │
  │       └─ "claude_code"   → acp.run_prompt(task, cwd, timeout)
  │                             └─ claude-agent-sdk query()
  │                             └─ Stream AssistantMessage/ResultMessage
  │                             └─ Truncate output at 8000 chars
  │
  └─ Return list of tool_result dicts
      → Appended to session history as "user" message
      → Provider called again with updated history
```

### Tool Schema

Each tool is defined as a dict with Anthropic's tool_use schema:

```python
{
    "name": "tool_name",
    "description": "...",
    "input_schema": {
        "type": "object",
        "properties": { ... },
        "required": ["..."],
    },
}
```

Registered in `ALL_TOOLS` list, passed to provider in every API call when `TOOLS_ENABLED=true`.

---

## Memory System

### Storage

```
workspace/memory/
  ├─ memory.db              # SQLite database
  │   ├─ memories           # Main table (id, content, tags, source, created_at)
  │   ├─ memories_fts       # FTS5 virtual table (content, tags) — auto-synced via triggers
  │   └─ embeddings         # Optional vectors (memory_id, vector BLOB)
  │
  └─ YYYY-MM-DD.md          # Daily Markdown logs (human-readable mirror)
```

### Search Pipeline

```
search(query)
  │
  ├─ BM25 Search (always):
  │   └─ FTS5 MATCH query → rank → normalize to 0..1
  │       └─ Fallback: prefix search on FTS5 syntax error
  │
  ├─ Vector Search (if OPENAI_API_KEY set):
  │   ├─ Get query embedding via OpenAI text-embedding-3-small (1536 dims)
  │   └─ Brute-force cosine similarity over all stored embeddings
  │       └─ Normalize to 0..1
  │
  └─ Merge:
      ├─ Both available: weighted merge (BM25 × 0.4 + vector × 0.6)
      ├─ BM25 only: BM25 results
      └─ Vector only: vector results
      → Return top N formatted results
```

---

## OAuth Authentication

### Anthropic (Claude)

```
setup.py → setup_claude():
  ├─ Generate PKCE: code_verifier + code_challenge (SHA256, base64url)
  ├─ Open browser → claude.ai/oauth/authorize
  │   Params: client_id, response_type=code, redirect_uri, scope, code_challenge
  ├─ User pastes authorization code
  ├─ POST console.anthropic.com/v1/oauth/token (code exchange)
  └─ save_credentials() → .credentials.json (0o600)

Runtime:
  ├─ load_credentials() → read .credentials.json
  ├─ Use access_token in Authorization: Bearer header
  └─ On 401: refresh_token() → retry
```

Scopes: `org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers`

### Codex (OpenAI — Device Auth / Headless)

```
setup.py → setup_codex():
  ├─ POST auth.openai.com/api/accounts/deviceauth/usercode
  │   Body: {client_id}
  │   Response: {device_auth_id, user_code, interval}
  │
  ├─ Display to user:
  │   "Visit: https://auth.openai.com/codex/device"
  │   "Enter code: XXXX-XXXX"
  │
  ├─ Poll: POST auth.openai.com/api/accounts/deviceauth/token
  │   Body: {device_auth_id, user_code}
  │   Wait: interval + 3s safety margin
  │   Until 200 → {authorization_code, code_verifier}
  │
  ├─ Exchange: POST auth.openai.com/oauth/token
  │   Body: grant_type=authorization_code, code, redirect_uri, client_id, code_verifier
  │   Response: {access_token, refresh_token, id_token, expires_in}
  │
  ├─ Extract account_id from JWT claims (for org subscriptions)
  └─ save_credentials() → .codex_credentials.json (0o600)

Runtime:
  ├─ _get_auth() → load + auto-refresh if expires_at < now
  ├─ Headers: Authorization: Bearer, ChatGPT-Account-Id (if org)
  └─ On 401: refresh_token() → retry
```

Token URL: `https://auth.openai.com/oauth/token`
API endpoint: `https://chatgpt.com/backend-api/codex/responses`
Allowed models: gpt-5.1-codex, gpt-5.2-codex, gpt-5.3-codex, gpt-5.1-codex-mini, gpt-5.1-codex-max

---

## Streaming Display

```
_send_streaming(message, session_key, user_content)
  │
  ├─ buffer = ""
  ├─ async for chunk in llm.stream(session_key, user_content):
  │   │
  │   ├─ First message: send when ≥5 chars OR 0.3s elapsed
  │   │   └─ message.reply(buffer + " ▍")     # Cursor indicator
  │   │
  │   └─ Subsequent: edit existing message when:
  │       ├─ ≥0.1s since last edit AND ≥50 new chars, OR
  │       └─ ≥100 new chars (force update)
  │       └─ sent_msg.edit(buffer[:1990] + " ▍")
  │
  └─ Final:
      ├─ ≤2000 chars: edit with full content (remove cursor)
      └─ >2000 chars: edit first 2000, send overflow as follow-up messages
```

---

## Configuration

Configuration is split between two files:

- **`config.yaml`** — non-sensitive settings (models, feature flags, timeouts, gateway options). Checked into git.
- **`.env`** — secrets only (tokens, API keys). Gitignored.

### config.yaml sections

| Section | Key settings |
|---------|-------------|
| `llm` | `provider`, `anthropic.model`, `codex.model`, `max_history`, `max_tokens`, `tools_enabled` |
| `discord` | `greeting_channel_id`, `allowed_dm_users`, `auto_reply.*`, `stream.*` |
| `gateway.voice` | `enabled`, wake words, STT/TTS provider + model, audio thresholds |
| `gateway.sms` | `enabled`, `webhook_port`, `webhook_url` |
| `gateway.imessage` | `enabled`, `cli_path`, `allow_from` |
| `gateway.api` | `enabled`, `host`, `port`, `api_key` |
| `gateway.heartbeat` | `enabled`, `interval`, `channel_id`, active hours |
| `storage` | `backend` (`sqlite`/`postgres`), SQLite paths |
| `services.google_calendar` | `enabled`, calendar IDs |
| `services.cron` | `enabled`, timezone, concurrency, tick interval |
| `services.health` | `enabled` |
| `services.timeouts` | `http_read`, `http_connect`, `exec_default`, `exec_max`, `acp_max` |

### Secrets (`.env`)

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_BOT_TOKEN` | **yes** | Discord bot token |
| `OPENAI_API_KEY` | no | Enables OpenAI STT/TTS + vector embeddings for memory search |
| `GITHUB_TOKEN` | no | GitHub PAT for gh CLI in exec tool |
| `ACP_CWD` | no | Default working directory for claude_code tool |
| `DATABASE_URL` | no | PostgreSQL connection string (enables Postgres backend) |
| `TWILIO_ACCOUNT_SID` | no | Twilio account SID (SMS gateway) |
| `TWILIO_AUTH_TOKEN` | no | Twilio auth token |
| `TWILIO_FROM_NUMBER` | no | Twilio outbound phone number |
| `VOLCENGINE_APP_ID` | no | Volcengine TTS app ID |
| `VOLCENGINE_TOKEN` | no | Volcengine TTS token |
| `GOOGLE_CREDENTIALS_FILE` | no | Path to Google service account credentials |

### System Prompt Assembly

```python
SYSTEM_PROMPT = read("workspace/SOUL.md") + "\n\n---\n\n" + read("workspace/IDENTITY.md")
# Fallback: "You are a helpful assistant."
```

---

## Development Commands

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
pip install -e ".[dev]"            # dev dependencies (pytest, coverage)
python setup.py                    # interactive OAuth + Discord token setup
python main.py                     # run the bot
```

## Testing

```bash
pytest                             # run all tests
pytest -v                          # verbose output
pytest --cov=bot                   # with coverage report
pytest --cov=bot --cov-report=term-missing  # show uncovered lines
pytest tests/test_message.py       # single file
pytest -k "test_tool"              # pattern match
```

- `pytest` + `pytest-asyncio` (auto mode: async tests run without decorators).
- All external dependencies (Discord, Claude API, OpenAI) mocked — tests run offline.
- `conftest.py` injects fake env vars via `pytest_configure` hook (before any `bot.*` import).
- SQLite tests use `tmp_path` fixtures to isolate DB state per test.
- `FakeProvider` (in conftest) provides controllable stream/call responses for processor tests.
- Coverage threshold: 60% (enforced by `pytest-cov`). Current: ~69%.

## Coding Style

- snake_case for functions/variables, UPPERCASE for constants.
- Type hints on function signatures.
- Keep the codebase minimal; avoid unnecessary abstractions.
- Credentials in `.credentials.json` (0o600) or `.env`; never hardcode secrets.

## Security

- Never commit `.env`, `.credentials.json`, or any real tokens.
- OAuth credentials file must have 0o600 permissions.
- ACP auto-approves all Claude Code permissions (personal bot assumption).

## Active Technologies
- Python 3.13+ + discord.py, httpx, google-auth-oauthlib, google-api-python-clien (001-google-calendar-plugin)
- SQLite (existing cron_jobs table for reminders), file-based credentials (.google_credentials.json) (001-google-calendar-plugin)
- Python 3.13+ + discord.py, httpx, asyncpg (new), pgvector-python (new) (002-postgres-storage)
- PostgreSQL 16 (Neon serverless) with pgvector extension; SQLite fallback (002-postgres-storage)

## Recent Changes
- 001-google-calendar-plugin: Added Python 3.13+ + discord.py, httpx, google-auth-oauthlib, google-api-python-clien
