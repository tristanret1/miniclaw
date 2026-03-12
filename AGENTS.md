# MiniClaw — Repository Guidelines

- Repo: minimal Discord chatbot powered by Claude (Anthropic OAuth 2.0 PKCE)
- Language: Python 3.13+
- No build step; no test framework configured yet.

## Project Structure

- `main.py` — entry point (`python main.py` to run, `python setup.py` for first-time setup)
- `bot/` — core modules:
  - `config.py` — env loading + system prompt assembly from `workspace/` files
  - `client.py` — Discord client, event handlers, streaming reply, image extraction
  - `claude.py` — Claude API calls (streaming + non-streaming), tool-use loop, auto-flush
  - `oauth.py` — OAuth 2.0 PKCE flow, credential save/load/refresh
  - `tools.py` — tool definitions (exec, memory_save, memory_search, claude_code)
  - `memory.py` — SQLite + FTS5/BM25 + optional vector hybrid search
  - `sessions.py` — SQLite-backed conversation persistence
  - `acp.py` — ACP client for Claude Code integration (JSON-RPC 2.0 over NDJSON)
  - `logger.py` — logging config (stdout + rotating file)
- `workspace/` — personality bootstrap files injected into system prompt:
  - `SOUL.md` — behavior principles, language preferences
  - `IDENTITY.md` — agent name, emoji, vibe
  - `memory/` — memory database + daily Markdown logs (gitignored)
  - `sessions.db` — conversation history (gitignored)
- `.credentials.json` — auto-generated OAuth tokens (never commit)
- `.env` — runtime config (never commit)

## Development Commands

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python setup.py        # interactive OAuth + Discord token setup
python main.py         # run the bot
```

## Coding Style

- Standard Python conventions: snake_case for functions/variables, UPPERCASE for constants.
- Use type hints on function signatures.
- Keep the codebase minimal; avoid unnecessary abstractions.
- Credentials go in `.credentials.json` (0o600 perms) or `.env`; never hardcode secrets.

## Key Design Decisions

- Session history persisted in SQLite (`workspace/sessions.db`); loaded lazily on first message.
- In-memory cache sits on top of DB for fast access within a session.
- Memory system: SQLite + FTS5 for BM25 keyword search, optional OpenAI embeddings for hybrid vector search.
- Streaming: Claude API responses streamed via SSE; Discord messages edited progressively.
- Multimodal: Discord image attachments extracted and sent as `image` content blocks.
- ACP: Claude Code integration via JSON-RPC 2.0 over NDJSON/stdio; singleton process reused across calls.
- Discord messages split at 2000 chars (Discord limit).
- OAuth token refresh happens automatically on 401 (single retry).
- System prompt assembled from `workspace/SOUL.md` + `workspace/IDENTITY.md`.

## Security

- Never commit `.env`, `.credentials.json`, or any real tokens.
- OAuth credentials file must have 0o600 permissions.
- ACP auto-approves all Claude Code permissions (personal bot assumption).
