# Changelog

## v0.3.0 (planned)

### Changes
- Skill system: load SKILL.md from `skills/` directory, Clawhub format compatible
- Skill prompt injection into system prompt
- Slash command dispatch (`/skill-name args`)

## v0.2.0 (2026-03-17)

### Changes
- **Refactor**: split monolithic `claude.py` into layered architecture
  - `bot/message.py` — unified message types (`Message`, `Content`, content builders)
  - `bot/provider/` — provider abstraction layer (`BaseProvider`, `AnthropicProvider`)
  - `bot/provider/transform.py` — message sanitization middleware per provider
  - `bot/session.py` — `SessionManager` with in-memory cache + SQLite persistence (replaces `sessions.py`)
  - `bot/processor.py` — `StreamProcessor` for tool loop, content accumulation, auto-flush
  - `bot/llm.py` — unified entry point (`stream()` / `reply()`)
- **Removed**: `bot/claude.py`, `bot/sessions.py` (logic distributed across new modules)
- Architecture now supports adding new LLM providers (OpenAI, Gemini, etc.) via `BaseProvider`
- **Testing**: added pytest test suite with 117 tests (~69% coverage)
  - `pyproject.toml` with pytest/coverage config
  - `tests/conftest.py` with shared fixtures (FakeProvider, temp DBs, fake credentials)
  - Tests for all modules: message, transform, session, memory, processor, llm, tools, oauth, client, provider
  - `pytest-asyncio` auto mode for async tests; all external APIs mocked
- `bot/config.py`: `DISCORD_BOT_TOKEN` now uses `os.environ.get()` (testable without .env); runtime guard moved to `main.py`

## v0.1.0 (2026-03-11)

### Changes
- Discord bot with Claude API (OAuth 2.0 PKCE)
- Streaming replies (currently disabled pending bug fix)
- Multimodal support (image attachments)
- Tool use: exec, memory_save, memory_search, claude_code, discord_send
- Memory system: SQLite + FTS5/BM25 + optional vector embeddings
- Conversation persistence (SQLite)
- Claude Code integration via claude-agent-sdk (ACP)
- Auto-reply mode with configurable channels/keywords/chance
- Message debounce (wait for edits before replying)
- GitHub token support for gh CLI
- 400 error auto-recovery (sanitize history and retry)
