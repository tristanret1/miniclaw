# Changelog

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
