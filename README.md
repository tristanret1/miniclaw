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

## Knowledge Base

Personal knowledge base system — ingest sources via conversation, auto-compile into a structured Obsidian-compatible wiki, and do deep research queries.

### Setup

Knowledge base is enabled by default. Configure in `config.yaml`:

```yaml
services:
  kb:
    enabled: true
    root: ~/kb            # where the KB lives (Obsidian vault)
    auto_compile: true    # auto-update wiki after each ingest
    compile_timeout: 600  # ACP compilation timeout (seconds)
    query_timeout: 300    # ACP research timeout (seconds)
```

Open `~/kb` as an Obsidian vault to browse the wiki with rendered wikilinks.

### CLI Usage

```bash
# Ingest a web article
uv run python main.py kb ingest https://lilianweng.github.io/posts/2023-06-23-agent/

# Ingest a PDF paper
uv run python main.py kb ingest https://arxiv.org/pdf/2401.12345.pdf

# Ingest a YouTube video (extracts transcript via yt-dlp)
uv run python main.py kb ingest https://www.youtube.com/watch?v=zjkBMFhNj_g

# Ask a research question (deep multi-article research via ACP)
uv run python main.py kb query "What are the key differences between RAG and long-context approaches?"

# View the wiki index
uv run python main.py kb list

# Check ingest/compile status
uv run python main.py kb status

# Manually trigger wiki compilation
uv run python main.py kb compile
```

### Chat Usage (Discord / Feishu)

The bot recognizes knowledge base intent and calls the `kb` tool automatically:

```
User: 帮我把这篇论文加到知识库 https://arxiv.org/pdf/2401.12345.pdf
Bot:  Saved to raw/2026-04-03-2401-12345.pdf. Auto-compiling wiki...

User: 知识库里关于 attention mechanism 有哪些内容？
Bot:  [ACP agent reads wiki/index.md, finds related articles,
       cross-references sources, returns comprehensive answer]

User: 把这个视频整理一下 https://youtube.com/watch?v=zjkBMFhNj_g
Bot:  Saved to raw/2026-04-03-zjkBMFhNj_g.md. Auto-compiling wiki...

User: kb status
Bot:  KB root: /Users/sen/kb
      Raw files: 3 total, 3 compiled, 0 pending
      Wiki: 5 concepts, 3 summaries, 1 queries
      Pending: none
```

### How It Works

```
Ingest:  URL → browser/curl/yt-dlp → raw/*.md|pdf
              → ACP compiles wiki (background)
                → wiki/summaries/ (per-source summary)
                → wiki/concepts/ (cross-source concept articles)
                → wiki/index.md (master index)
                → wiki/connections.md (backlinks)

Query:   Question → ACP reads index → follows references
              → reads relevant articles → cross-references
              → writes answer → saves to wiki/queries/
```

### Directory Structure

```
~/kb/
├── CLAUDE.md              # Wiki compilation spec (auto-generated, read by ACP)
├─�� raw/                   # Original sources (never modified by compiler)
│   ├── 2026-04-03-agent.md
│   ├── 2026-04-03-2401-12345.pdf
│   └── 2026-04-03-zjkBMFhNj_g.md
├── wiki/                  # LLM-compiled knowledge base
│   ├── index.md           # Master index (alphabetical, one-line summaries)
│   ├── concepts/          # Concept articles with [[wikilinks]]
│   ├── summaries/         # Per-source summaries
│   ├── queries/           # Archived research Q&A
│   └── connections.md     # Inter-concept relationship map
└── .kb_state.json         # Tracks which raw files have been compiled
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
