# Changelog

## v0.2.1 (2026-03-14)

### Changes
- Cron scheduler: asyncio-based with SQLite storage (`workspace/cron.db`)
- Three schedule types: `every` (interval), `cron` (expression), `at` (one-shot)
- Concurrent job execution via `asyncio.gather()` + `Semaphore(CRON_MAX_CONCURRENT)`
- Per-job context: `context` (custom system instructions), `model` (model override), `session_mode` (isolated/persistent)
- Isolated agent sessions: `run_isolated_turn()` — ephemeral, no history persistence, no auto-flush
- Persistent sessions: `cron:{job.id}` session key, conversation history carries across runs
- New tools: `cron_create`, `cron_list`, `cron_delete`
- `_build_request_body()` and `get_reply_stream()` now accept optional `system_prompt` and `model` overrides (backward-compatible)
- Exponential backoff on consecutive errors (30s → 1m → 5m → 15m → 1h)
- One-shot jobs auto-disable after execution
- New dependency: `croniter>=2.0`
- New config: `CRON_ENABLED`, `CRON_TIMEZONE`, `CRON_MAX_CONCURRENT`

## v0.2.0 (2026-03-13)

### Changes
- Skill system: load SKILL.md from `skills/` directory, Clawhub format compatible
- Skill prompt injection into system prompt (`<available-skills>` XML block)
- Slash command dispatch (`/skill-name args`) with skill context injection
- `/skills` command to list available skills
- Dependency checking: `requires.bins`, `requires.anyBins`, `requires.env`
- Built-in example skills: github (gh CLI), snow-forecast (ski resort snowfall via Open-Meteo)
- New dependency: `pyyaml>=6.0`

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
