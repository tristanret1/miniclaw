# Data Model: Google Calendar Integration Plugin

**Branch**: `001-google-calendar-plugin` | **Date**: 2026-03-23

## Entities

### CalendarConfig

Represents a configured Google Calendar connection. Stored as environment variables, not in a database.

| Field | Type | Description |
| ----- | ---- | ----------- |
| calendar_id | string | Google Calendar ID (email-like, e.g., `user@gmail.com` or `abc123@group.calendar.google.com`) |
| display_name | string | Human label: "Life" or "Work" |
| access_mode | enum | `read_write` (Life) or `read_only` (Work) |

**Constraints**:
- Exactly two calendars configured per bot instance
- Life calendar: `GOOGLE_CALENDAR_LIFE_ID` env var
- Work calendar: `GOOGLE_CALENDAR_WORK_ID` env var
- Access mode is determined by display_name (Life → read_write, Work → read_only)

### Event (Google Calendar API response, mapped)

Represents a calendar event as returned by the Google Calendar API and formatted for bot responses.

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| id | string | yes | Google Calendar event ID (used for update/delete) |
| title | string | yes | Event summary/title |
| start | datetime (tz-aware) | yes | Start time in user's timezone |
| end | datetime (tz-aware) | yes | End time in user's timezone |
| description | string | no | Event description/notes |
| location | string | no | Event location |
| source_calendar | enum | yes | "Life" or "Work" — derived from which calendar returned the event |
| is_all_day | boolean | yes | Whether this is an all-day event (date vs datetime) |

**Constraints**:
- Events are not stored locally — always fetched from Google Calendar API
- Event ID is opaque; used only for update/delete operations
- All-day events use `date` field; timed events use `dateTime` field (Google API convention)

### UrgentReminder (stored as a cron job)

Represents a scheduled reminder for an urgent personal event. Implemented as a one-shot cron job.

| Field | Type | Required | Description |
| ----- | ---- | -------- | ----------- |
| cron_job_id | string | yes | ID of the cron job backing this reminder |
| event_id | string | yes | Google Calendar event ID this reminder is for |
| event_title | string | yes | Event title (for the reminder message) |
| fire_at | datetime | yes | When to trigger the reminder (event_start - offset) |
| reminder_offset | duration | yes | How far before the event (default: 15 minutes) |
| primary_channel | enum | yes | "phone_call", "sms", or "imessage" (default: "phone_call") |

**Constraints**:
- Stored via existing cron system (`cron_jobs` SQLite table) with `schedule_type="at"`
- One-shot: `enabled` set to 0 after firing
- If event time is modified, the corresponding cron job must be deleted and recreated
- Cascade fallback order: phone_call → sms → Discord message

**State Transitions**:
```
Created → Scheduled (cron job active, waiting)
Scheduled → Fired (cron job executes, attempts primary channel)
Fired → Delivered (primary or fallback channel succeeded)
Fired → Failed (all channels failed — logged, user notified via Discord)
Scheduled → Cancelled (event deleted or rescheduled — cron job deleted)
```

### GoogleCredential (file-based)

OAuth 2.0 tokens for Google Calendar API access. Stored in `.google_credentials.json`.

| Field | Type | Description |
| ----- | ---- | ----------- |
| access_token | string | Current access token |
| refresh_token | string | Long-lived refresh token |
| expires_at | float | Unix timestamp when access_token expires |
| client_id | string | Google OAuth client ID |
| client_secret | string | Google OAuth client secret |
| scopes | list[string] | Granted OAuth scopes |

**Constraints**:
- File permissions: 0o600 (owner read/write only)
- Auto-refresh when `expires_at < now`
- If refresh fails, user must re-run setup

## Relationships

```
CalendarConfig (Life) ──1:N──► Event
CalendarConfig (Work) ──1:N──► Event (read-only)
Event (Life, urgent) ──1:0..1──► UrgentReminder
GoogleCredential ──1:1──► Google Calendar API access
```

## No New Database Tables

This feature does not introduce new SQLite tables. Data storage:
- **Events**: Fetched live from Google Calendar API (no local cache)
- **Reminders**: Stored as cron jobs in existing `cron_jobs` table
- **Credentials**: File-based (`.google_credentials.json`)
- **Config**: Environment variables (`.env`)
