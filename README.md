# MiniClaw

Minimal Discord chatbot powered by Claude / Codex (multi-provider). Supports streaming responses, tool use, long-term memory, voice, iMessage/SMS gateways, and more.

## Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- Discord bot token ([Developer Portal](https://discord.com/developers/applications))
- Anthropic account (Claude) and/or OpenAI account (Codex)

macOS additional (for voice/pyaudio):

```bash
brew install portaudio
```

## Quick Start

```bash
# 1. Install dependencies
uv sync --dev

# 2. Copy env template and fill in your secrets
cp .env.example .env
# edit .env — at minimum set DISCORD_BOT_TOKEN

# 3. Run interactive OAuth setup (Claude / Codex / Google Calendar)
uv run python setup.py

# 4. Start the bot
uv run python main.py
```

## Configuration

| File | Purpose |
|------|---------|
| `config.yaml` | Non-sensitive settings — models, features, timeouts, gateways |
| `.env` | Secrets only — tokens, API keys (gitignored) |
| `workspace/SOUL.md` | Bot personality and behavior principles |
| `workspace/IDENTITY.md` | Bot name, emoji, vibe |

### Providers

Set `llm.provider` in `config.yaml`:

- **`anthropic`** — Claude (default), uses OAuth credentials
- **`codex`** — OpenAI Codex, uses device auth flow

## Testing

```bash
uv run pytest                    # all tests
uv run pytest -v                 # verbose
uv run pytest --cov=bot          # with coverage
```

## Agent Management UI

Agent configuration (personality, identity, LLM settings) can be stored in PostgreSQL and managed via a web UI.

### Setup

```bash
# Start the API server
DATABASE_URL=your-postgres-url uv run uvicorn web.api.main:app --port 8000

# Start the frontend (separate terminal)
cd web/app && bun run dev
```

Open http://localhost:3000 to create and manage agents.

### Migration from local files

If you have existing agents in `agents.json` or `workspace/`:

```bash
uv run python scripts/migrate_agents_to_db.py
```

## Project Structure

```
bot/
├── client.py          # Discord event handlers, streaming display
├── llm.py             # Unified LLM entry point
├── processor.py       # Stream processor, tool loop
├── provider/          # LLM provider abstraction (Anthropic, Codex)
├── tools/             # Tool definitions (exec, memory, claude_code, etc.)
├── gateway/           # Non-Discord gateways (voice, iMessage, SMS, API)
├── storage/           # Session & memory persistence (SQLite / PostgreSQL)
├── services/          # External service clients (Google Calendar, Twilio)
└── oauth/             # OAuth credential management
```

## License

Private project.
