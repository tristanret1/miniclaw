# Research: Google Calendar Integration Plugin

**Branch**: `001-google-calendar-plugin` | **Date**: 2026-03-23

## 1. Google Calendar API Authentication

**Decision**: Use `google-auth-oauthlib` for OAuth 2.0 Authorization Code Flow with browser-based consent.

**Rationale**: The project already has two OAuth implementations (Anthropic PKCE in `oauth.py`, Codex device auth in `codex_oauth.py`). Google's official `google-auth-oauthlib` library handles the full OAuth 2.0 flow including automatic token refresh, which is consistent with the project's credential management pattern. Using the official library avoids reimplementing token refresh logic.

**Alternatives considered**:
- Raw httpx OAuth (like Anthropic): More control but more code to maintain; Google's token endpoints have nuances the official library handles.
- Service account: Simpler auth but doesn't support user-owned personal calendars well; designed for server-to-server, not personal bot use.

**Scopes**:
- Life calendar: `https://www.googleapis.com/auth/calendar` (full read-write)
- Work calendar: `https://www.googleapis.com/auth/calendar.readonly` (read-only)
- Single OAuth consent covers both scopes.

## 2. Credential Storage

**Decision**: Store Google OAuth tokens in `.google_credentials.json` (0o600 permissions), following the existing pattern.

**Rationale**: Consistent with `.credentials.json` (Anthropic) and `.codex_credentials.json` (Codex). Same `save_credentials()` / `load_credentials()` pattern. File is already in `.gitignore` pattern.

**Alternatives considered**:
- Environment variable for tokens: Fragile for multi-field tokens with refresh capability.
- Keychain/system credential store: Platform-specific, inconsistent with existing approach.

## 3. Calendar API Client Library

**Decision**: Use `google-api-python-client` (`googleapiclient`) as the Calendar API wrapper.

**Rationale**: Official Google library, handles pagination, timezone conversion, and event CRUD. Well-documented. All calendar operations (list, insert, update, delete) are single method calls.

**Alternatives considered**:
- Raw httpx REST calls: More consistent with existing codebase style (Anthropic/Codex use httpx), but Google Calendar API has complex query parameters and pagination that the official client handles better.
- `gcsa` (Google Calendar Simple API): Lighter wrapper but less maintained and adds an indirect dependency.

## 4. Tool Architecture

**Decision**: Single `google_calendar` tool with an `action` parameter, rather than separate tools per operation.

**Rationale**: The bot already has 10+ tools. Adding 4 separate calendar tools (list, create, update, delete) would bloat the tool list. A single tool with `action` enum keeps the tool count manageable and reduces prompt token usage. Claude can reason about which action to use within a single tool call.

**Alternatives considered**:
- Separate tools per operation (google_calendar_list, google_calendar_create, etc.): Cleaner separation but adds 4 entries to ALL_TOOLS, increasing every API call's token count.
- Hybrid (read tool + write tool): Middle ground but arbitrary split.

## 5. Urgent Event Reminders

**Decision**: Use the existing cron system (`cron.create_job`) to schedule one-shot reminder jobs for urgent events.

**Rationale**: The cron system already supports one-shot scheduling via `schedule_type="at"` with `schedule_value="+Xm"` or ISO datetime. It already handles delivery to Discord, SMS, and phone call channels. No new infrastructure needed — just create a cron job when an urgent event is created.

**Implementation**:
1. When `google_calendar` tool creates an urgent event, it also calls `cron.create_job()` with:
   - `schedule_type="at"`, `schedule_value=<event_time - reminder_offset>`
   - `payload="Urgent reminder: {event_title} starts in {offset} minutes"`
   - `delivery_channel="sms"` or phone call via the payload instructing Claude to use `phone_call` tool
2. Cascade fallback: The cron job payload instructs Claude to call `phone_call` first, fall back to `sms`, then Discord.

**Alternatives considered**:
- Custom reminder scheduler: Unnecessary duplication of cron functionality.
- Google Calendar native reminders: Only supports email/popup, not phone calls or Discord messages.

## 6. Calendar ID Configuration

**Decision**: Store Life and Work calendar IDs as environment variables (`GOOGLE_CALENDAR_LIFE_ID`, `GOOGLE_CALENDAR_WORK_ID`).

**Rationale**: Calendar IDs are stable identifiers (email-like strings). Environment variables are the project's standard config mechanism. Set once during `setup.py` and rarely changed.

**Alternatives considered**:
- Store in `.google_credentials.json`: Mixes auth with config; credentials may be refreshed/rotated.
- Hardcode: Not portable.

## 7. Timezone Handling

**Decision**: Reuse existing `CRON_TIMEZONE` config for calendar operations. All events are stored and displayed in the user's configured timezone.

**Rationale**: The cron system already uses `CRON_TIMEZONE` (default: `America/Vancouver`). Google Calendar API supports timezone parameters on all requests. Single source of truth avoids timezone mismatches between calendar events and cron reminders.

**Alternatives considered**:
- Separate `GOOGLE_CALENDAR_TIMEZONE`: Unnecessary unless user wants different timezone for calendar vs cron (unlikely for a personal bot).

## 8. New Dependencies

| Package | Purpose | Version |
| ------- | ------- | ------- |
| `google-auth-oauthlib` | OAuth 2.0 browser flow + token refresh | `>=1.0` |
| `google-api-python-client` | Calendar API client (list, create, update, delete) | `>=2.0` |
| `google-auth` | Base auth library (transitive, but pin for clarity) | `>=2.0` |

Note: `google-auth-httplib2` is NOT needed — `google-api-python-client` can use `google-auth` directly with httpx or the built-in transport.
