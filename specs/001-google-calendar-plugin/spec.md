# Feature Specification: Google Calendar Integration Plugin

**Feature Branch**: `001-google-calendar-plugin`
**Created**: 2026-03-23
**Updated**: 2026-03-23
**Status**: Draft
**Input**: User description: "添加一个插件集成Google Calendar，支持两个不同的calendar（生活和工作）。查看summary合并显示，创建只创建个人事物，工作calendar只读。"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - View Merged Schedule Summary (Priority: P1)

As a user, I can ask the bot about my upcoming events and receive a single merged timeline from both my Life and Work calendars, with each event clearly labeled by its source calendar.

**Why this priority**: This is the foundational use case — a unified view of the day is the most common need. Without this, no other calendar features have value.

**Independent Test**: Can be fully tested by asking "what's on my calendar today?" and verifying events from both calendars appear in a single chronological list with correct labels.

**Acceptance Scenarios**:

1. **Given** a user with events on both calendars, **When** they ask "what's on my schedule today?", **Then** the bot returns a single merged list of events from both calendars, each labeled "[Life]" or "[Work]", sorted by start time.
2. **Given** a user asks about a specific date range, **When** they say "what do I have next week?", **Then** the bot returns all events from both calendars within that range, merged and sorted chronologically.
3. **Given** a user asks about a specific calendar, **When** they say "what work meetings do I have tomorrow?", **Then** the bot returns only events from the Work calendar.
4. **Given** no events exist in the requested range, **When** the user asks, **Then** the bot responds indicating no events found for the period.

---

### User Story 2 - Create Personal Events (Priority: P2)

As a user, I can ask the bot to create an event on my Life (personal) calendar by describing it in natural language. The bot always creates events on the Life calendar — work calendar is read-only.

**Why this priority**: Creating personal events through chat is the second most valuable capability. Since the user rarely creates work events through the bot, simplifying to Life-calendar-only creation reduces complexity and avoids mistakes.

**Independent Test**: Can be tested by saying "add dinner with friends Saturday at 7pm" and verifying the event appears on the Life calendar in Google Calendar.

**Acceptance Scenarios**:

1. **Given** a user describes a personal event, **When** they say "add dinner with friends Saturday 7pm", **Then** the event is created on the Life calendar with correct title, date, and time.
2. **Given** a user provides incomplete information, **When** they say "add a dentist appointment next Tuesday", **Then** the bot asks for missing details (time, duration) before creating on the Life calendar.
3. **Given** a user explicitly asks to create an event on the Work calendar, **When** they say "add a meeting to my work calendar", **Then** the bot informs them that event creation is only supported on the Life calendar and suggests using Google Calendar directly for work events.
4. **Given** a user creates an urgent event, **When** they say "add an urgent dentist appointment tomorrow at 2pm, remind me 30 minutes before by phone", **Then** the event is created on the Life calendar marked urgent, and a phone call reminder is scheduled 30 minutes before the event.
5. **Given** a user creates an urgent event without specifying reminder details, **When** they say "add urgent: pick up passport tomorrow 5pm", **Then** the event is created with a phone call reminder defaulting to 15 minutes before.

---

### User Story 3 - Daily Schedule Summary via Scheduled Delivery (Priority: P3)

As a user, I can set up a recurring daily briefing that automatically sends me my merged day's schedule each morning via Discord.

**Why this priority**: Proactive notifications add significant convenience but depend on the cron system already in place and the core merged calendar view (P1).

**Independent Test**: Can be tested by creating a scheduled job that triggers a calendar summary and verifying the message arrives in Discord at the configured time.

**Acceptance Scenarios**:

1. **Given** a user requests a daily briefing, **When** they say "send me my schedule every morning at 8am", **Then** the bot creates a recurring job that delivers a merged calendar summary daily.
2. **Given** a daily briefing is configured and the user has events, **When** the scheduled time arrives, **Then** the bot sends a formatted merged summary of today's events from both calendars, labeled by source. Urgent events are visually highlighted with a marker and their scheduled reminder time is displayed.
3. **Given** a daily briefing is configured and the user has no events, **When** the scheduled time arrives, **Then** the bot sends a brief "no events today" message.

---

### User Story 4 - Modify or Delete Personal Events (Priority: P4)

As a user, I can ask the bot to update or cancel existing events on my Life calendar. Work calendar events are read-only.

**Why this priority**: Modification is less frequent than reading or creating, and users can fall back to the Google Calendar app for edits.

**Independent Test**: Can be tested by saying "cancel my dinner on Friday" and verifying the event is removed from the Life calendar.

**Acceptance Scenarios**:

1. **Given** a user wants to reschedule a personal event, **When** they say "move my dinner to 8pm", **Then** the bot updates the event time on the Life calendar.
2. **Given** a user wants to cancel a personal event, **When** they say "cancel the dentist appointment on Tuesday", **Then** the bot deletes the event after confirming with the user.
3. **Given** a user tries to modify a Work calendar event, **When** they say "cancel my 3pm work meeting", **Then** the bot informs them that work events can only be viewed, not modified, and suggests using Google Calendar directly.
4. **Given** multiple events match the description, **When** the user says "cancel my event tomorrow", **Then** the bot lists matching Life calendar events and asks which one to cancel.

---

### Edge Cases

- What happens when the Google Calendar service is unreachable or rate-limited? The bot should inform the user and suggest retrying later.
- What happens when the user's authentication token expires? The bot should attempt to refresh automatically; if that fails, guide the user through re-authentication.
- What happens when event times are ambiguous (e.g., "3pm" without timezone)? The bot should use the user's configured timezone.
- What happens when creating an event that conflicts with an existing event on the Life calendar? The bot should warn the user about the conflict but still allow creation if confirmed.
- What happens when the user asks to create/modify a work event? The bot should clearly explain that the Work calendar is read-only and suggest using Google Calendar directly.
- What happens when an urgent event reminder fails (e.g., phone call skill unavailable)? The bot should cascade: phone call → SMS → Discord message, and notify the user which channel was used.
- What happens when a user edits an urgent event's time? The reminder schedule should automatically update to match the new event time.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST support connecting to exactly two Google Calendars, designated as "Life" (personal, read-write) and "Work" (read-only).
- **FR-002**: System MUST authenticate with Google Calendar using credentials stored securely with restricted file permissions (consistent with existing credential storage patterns).
- **FR-003**: System MUST list events from both calendars as a single merged, chronologically sorted timeline for a specified date or date range.
- **FR-004**: System MUST support filtering events by a specific calendar when the user requests it (e.g., "only work events").
- **FR-005**: System MUST create events exclusively on the Life calendar with title, start time, end time, and optional description.
- **FR-006**: System MUST reject attempts to create or modify events on the Work calendar with a clear, helpful message.
- **FR-007**: System MUST update existing Life calendar events (reschedule, rename, change description).
- **FR-008**: System MUST delete Life calendar events after user confirmation.
- **FR-009**: System MUST label each event with its source calendar ("[Life]" or "[Work]") in all responses.
- **FR-010**: System MUST handle timezone-aware scheduling using the user's configured timezone.
- **FR-011**: System MUST support natural language date/time parsing through the LLM, converting phrases like "next Tuesday at 3pm" into actual dates before calling the calendar tool.
- **FR-012**: System MUST integrate with the existing scheduled job system to support recurring calendar summaries.
- **FR-013**: System MUST gracefully handle service errors, token expiration, and rate limits with user-friendly messages.
- **FR-014**: System MUST refresh expired authentication tokens automatically without user intervention.
- **FR-015**: System MUST support an optional urgency flag (normal/urgent) when creating personal events on the Life calendar.
- **FR-016**: System MUST trigger a skill-based reminder for events marked as urgent, at a user-configurable time before the event starts (default: 15 minutes).
- **FR-017**: System MUST default to phone call as the reminder channel for urgent events, with user-overridable options of SMS or iMessage per event.
- **FR-018**: System MUST cascade through fallback channels if the primary reminder fails: phone call → SMS → Discord message. The user MUST be notified which channel was ultimately used.
- **FR-019**: System MUST visually distinguish urgent events in daily briefing summaries with a marker and display the scheduled reminder time.

### Key Entities

- **Calendar**: Represents a connected Google Calendar. Has a display name (Life/Work), a calendar identifier, access credentials, and an access mode (read-write for Life, read-only for Work).
- **Event**: Represents a calendar event. Has a title, start time, end time, optional description, optional location, source calendar (Life/Work), a unique identifier for modifications, and an optional urgency flag (normal or urgent). Urgent events trigger skill-based reminders (e.g., phone call).
- **Calendar Credential**: Authentication information for Google Calendar access. Stored securely on the host with restricted permissions, supports automatic token refresh.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Users can retrieve their merged daily schedule from both calendars within 5 seconds of asking.
- **SC-002**: Users can create a new personal event through natural language in a single conversational exchange (no more than 2 follow-up questions from the bot).
- **SC-003**: Calendar events display correctly with proper timezone handling — events show in the user's local time.
- **SC-004**: Scheduled daily briefings are delivered within 2 minutes of the configured time.
- **SC-005**: Authentication token refresh succeeds transparently — users experience no authentication-related interruptions during normal use.
- **SC-006**: 100% of event creation requests go to the Life calendar — the bot never accidentally creates events on the Work calendar.
- **SC-007**: When asked about "my schedule" without specifying a calendar, events from both calendars appear in a single merged view every time.
- **SC-008**: Urgent event reminders are delivered successfully (via primary or fallback channel) at least 99% of the time.
- **SC-009**: Urgent events are visually distinguishable from normal events in every summary and briefing output.

## Clarifications

### Session 2026-03-23

- Q: How should event urgency be modeled? → A: Binary — normal (no extra reminder) vs urgent (triggers skill-based reminder).
- Q: How far in advance should urgent event reminders trigger? → A: User-configurable per event, default 15 minutes.
- Q: What is the default reminder skill for urgent events? → A: Phone call (default), user can override to SMS or iMessage per event.
- Q: What happens if the primary reminder skill fails? → A: Cascade automatically: phone call → SMS → Discord message.
- Q: Should urgent events be visually distinguished in daily briefings? → A: Yes, highlighted with a marker and reminder time shown.

## Assumptions

- The user (Sen) is the sole user of this bot instance — multi-user calendar support is not required.
- The user's two calendars are already created in Google — the bot connects to existing calendars, it does not create them.
- The Work calendar is always read-only through the bot — this is a deliberate simplification since the user rarely creates work events via the bot.
- Timezone is configured once (via environment variable or setup) and applies to all calendar operations.
- The bot operates as a personal assistant — it does not need to handle calendar sharing, invitations to others, or multi-attendee coordination.
- Natural language date parsing is handled by the LLM (Claude) rather than a dedicated NLP library — Claude interprets "next Tuesday" and converts it to an actual date before calling the calendar tool.
- Event creation defaults to 1-hour duration if the user does not specify an end time.
