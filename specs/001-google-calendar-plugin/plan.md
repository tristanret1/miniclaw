# Implementation Plan: Google Calendar Integration Plugin

**Branch**: `001-google-calendar-plugin` | **Date**: 2026-03-23 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/001-google-calendar-plugin/spec.md`

## Summary

Add a `google_calendar` tool to miniclaw that connects two Google Calendars (Life: read-write, Work: read-only), provides merged event listing, creates personal events on the Life calendar, and supports urgent event reminders via phone call/SMS cascade using the existing cron system.

## Technical Context

**Language/Version**: Python 3.13+
**Primary Dependencies**: discord.py, httpx, google-auth-oauthlib, google-api-python-client
**Storage**: SQLite (existing cron_jobs table for reminders), file-based credentials (.google_credentials.json)
**Testing**: pytest + pytest-asyncio (auto mode), all external APIs mocked
**Target Platform**: macOS / Linux server (personal bot)
**Project Type**: Discord chatbot with LLM tool use
**Performance Goals**: Calendar queries return within 5 seconds; reminders fire within 2 minutes of scheduled time
**Constraints**: Single user, two calendars, no local event cache
**Scale/Scope**: 1 user, ~50 events/week across 2 calendars

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Constitution is an unfilled template — no specific gates defined. Proceeding with project-level conventions from CLAUDE.md:
- ✅ snake_case functions, UPPERCASE constants
- ✅ Type hints on function signatures
- ✅ Minimal codebase, avoid unnecessary abstractions
- ✅ Credentials in dedicated file (0o600), never hardcoded
- ✅ Tests mock all external dependencies

**Post-Phase 1 re-check**: Design adheres to all conventions. Single tool with action parameter keeps codebase minimal. OAuth follows existing credential patterns.

## Project Structure

### Documentation (this feature)

```text
specs/001-google-calendar-plugin/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0: technology decisions
├── data-model.md        # Phase 1: entity models
├── quickstart.md        # Phase 1: developer setup guide
├── contracts/
│   └── google-calendar-tool.md  # Phase 1: tool interface contract
├── checklists/
│   └── requirements.md  # Spec quality validation
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
bot/
├── google_calendar.py       # NEW: Calendar API wrapper (list, create, update, delete)
├── google_oauth.py          # NEW: Google OAuth 2.0 flow + credential management
├── config.py                # MODIFY: Add GOOGLE_CALENDAR_* env vars
└── tools.py                 # MODIFY: Add google_calendar tool definition + handler

setup.py                     # MODIFY: Add setup_google() OAuth flow
.env.example                 # MODIFY: Add Google Calendar config template
requirements.txt             # MODIFY: Add google-auth-oauthlib, google-api-python-client
pyproject.toml               # MODIFY: Add new dependencies to dev/optional deps

tests/
├── test_google_calendar.py  # NEW: Calendar API wrapper tests (mocked)
└── test_tools.py            # MODIFY: Add google_calendar tool dispatch tests
```

**Structure Decision**: Follows existing project layout — new modules in `bot/`, tests in `tests/`. No new directories needed. The `google_calendar.py` module encapsulates all Google Calendar API interactions, while `google_oauth.py` handles authentication (mirroring the existing `oauth.py` / `codex_oauth.py` pattern).

## Key Design Decisions

### 1. Single Tool vs Multiple Tools

**Decision**: Single `google_calendar` tool with `action` parameter (list/create/update/delete).

**Reason**: The bot already has 10+ tools. Adding 4 separate tools would increase token usage on every API call. A single tool with an action enum is how Claude naturally reasons about CRUD operations.

### 2. No Local Event Cache

**Decision**: Always fetch events live from Google Calendar API.

**Reason**: Single-user bot with low query volume. Caching adds complexity (invalidation, staleness) without meaningful performance benefit. Google Calendar API is fast enough for interactive use.

### 3. Urgent Reminders via Cron

**Decision**: Reuse existing `cron.create_job()` with `schedule_type="at"` for one-shot reminders.

**Reason**: The cron system already handles scheduling, delivery channels (Discord/SMS), and error recovery. No new infrastructure needed.

### 4. Cascade Fallback in Reminder Payload

**Decision**: The cron job payload instructs Claude to attempt phone_call first, then fall back to SMS, then Discord message.

**Reason**: The cron execution flow already calls `llm.reply()` which gives Claude access to all tools. Claude can attempt `phone_call`, detect failure, and try `sms` within the same tool loop (up to 20 rounds).

### 5. Google OAuth via Official Library

**Decision**: Use `google-auth-oauthlib` for OAuth flow instead of raw httpx.

**Reason**: Google's token endpoints have nuances (PKCE, consent screens, scope handling) that the official library handles correctly. Reduces maintenance burden.

## File Change Summary

| File | Action | Description |
| ---- | ------ | ----------- |
| `bot/google_calendar.py` | Create | Calendar API wrapper: list_events, create_event, update_event, delete_event |
| `bot/google_oauth.py` | Create | OAuth 2.0 flow: authorize, save/load/refresh credentials |
| `bot/config.py` | Modify | Add GOOGLE_CALENDAR_* env vars |
| `bot/tools.py` | Modify | Add GOOGLE_CALENDAR_TOOL definition + handler in handle_tool_call() |
| `setup.py` | Modify | Add setup_google() interactive OAuth setup |
| `.env.example` | Modify | Add Google Calendar config template |
| `requirements.txt` | Modify | Add google-auth-oauthlib, google-api-python-client |
| `pyproject.toml` | Modify | Add dependencies |
| `tests/test_google_calendar.py` | Create | Unit tests for calendar wrapper (mocked API) |
| `tests/test_tools.py` | Modify | Add google_calendar tool dispatch tests |
