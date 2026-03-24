# Tasks: Google Calendar Integration Plugin

**Input**: Design documents from `/specs/001-google-calendar-plugin/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Included — project has established pytest conventions and 60% coverage threshold.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add dependencies and configuration for Google Calendar integration

- [x] T001 Add google-auth-oauthlib, google-api-python-client, and google-auth to requirements.txt
- [x] T002 [P] Add Google Calendar dependencies to pyproject.toml optional/dev deps
- [x] T003 Add GOOGLE_CALENDAR_ENABLED, GOOGLE_CALENDAR_CLIENT_ID, GOOGLE_CALENDAR_CLIENT_SECRET, GOOGLE_CALENDAR_LIFE_ID, GOOGLE_CALENDAR_WORK_ID config vars to bot/config.py (reuse CRON_TIMEZONE for calendar timezone)
- [x] T004 [P] Add Google Calendar config template to .env.example with comments explaining each variable

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Google OAuth authentication and Calendar API client — MUST be complete before ANY user story

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Create bot/google_oauth.py with save_credentials(), load_credentials(), refresh_credentials() functions. Store tokens in .google_credentials.json (0o600 permissions). Follow the pattern from bot/oauth.py and bot/codex_oauth.py. Include authorize() function that runs OAuth 2.0 browser flow via google-auth-oauthlib with scopes: calendar (read-write) + calendar.readonly
- [x] T006 Create bot/google_calendar.py with _build_service() function that initializes googleapiclient Calendar service using credentials from google_oauth.load_credentials(). Include auto-refresh on expired tokens. Add _parse_event() helper to convert Google API event dict to a standardized dict with fields: id, title, start, end, description, location, source_calendar, is_all_day
- [x] T007 Add setup_google() function to setup.py that runs interactive OAuth consent flow, prompts user for Life and Work calendar IDs, and writes them to .env. Integrate into existing setup flow (called after setup_codex or as a new menu option)
- [x] T008 Add .google_credentials.json to .gitignore if not already covered by existing patterns

**Checkpoint**: Google OAuth works end-to-end. `load_credentials()` returns valid tokens. `_build_service()` returns a Calendar API client.

---

## Phase 3: User Story 1 - View Merged Schedule Summary (Priority: P1) 🎯 MVP

**Goal**: Users can ask "what's on my calendar today?" and see a merged timeline from both Life and Work calendars, each event labeled by source.

**Independent Test**: Ask the bot "what's on my calendar today?" → verify events from both calendars appear chronologically with [Life]/[Work] labels.

### Implementation for User Story 1

- [x] T009 [US1] Implement list_events(calendar, date_start, date_end) in bot/google_calendar.py. Fetch events from Life calendar, Work calendar, or both. For "both": merge results sorted by start time. Each event dict includes source_calendar="Life" or "Work". Handle all-day events (date vs dateTime). Use CRON_TIMEZONE for timezone parameter. Return list of parsed event dicts
- [x] T010 [US1] Implement format_events(events) in bot/google_calendar.py. Convert list of event dicts to a formatted string matching the contract output format: "📅 Schedule for {date}:\n\n{time} [{calendar}] {title}\n...". Label urgent events with 🚨 marker. Handle empty list → "No events found for this period."
- [x] T011 [US1] Define GOOGLE_CALENDAR_TOOL dict in bot/tools.py matching the input_schema from contracts/google-calendar-tool.md. Add to ALL_TOOLS list (conditionally: only if GOOGLE_CALENDAR_ENABLED)
- [x] T012 [US1] Implement run_google_calendar(action, **kwargs) async handler in bot/tools.py. For action="list": validate date_start/date_end params, call list_events(), call format_events(), return formatted string. Handle errors: missing params → "Error: Missing required parameter: {name}", API errors → user-friendly messages, auth failure → "Error: Google Calendar authentication expired. Please re-run setup."
- [x] T013 [US1] Add "google_calendar" case to handle_tool_call() dispatcher in bot/tools.py. Route to run_google_calendar() with tool_input dict

### Tests for User Story 1

- [x] T014 [P] [US1] Create tests/test_google_calendar.py with tests for list_events() and format_events(). Mock googleapiclient service. Test: merged list from both calendars sorted by time, single calendar filter, empty results, all-day events, timezone handling, event labeling ([Life]/[Work])
- [x] T015 [P] [US1] Add google_calendar tool dispatch test to tests/test_tools.py. Mock run_google_calendar(). Verify handle_tool_call("google_calendar", {"action": "list", ...}) routes correctly

**Checkpoint**: User Story 1 fully functional. Bot can list merged events from both calendars via the google_calendar tool.

---

## Phase 4: User Story 2 - Create Personal Events (Priority: P2)

**Goal**: Users can create events on the Life calendar via natural language. Urgent events trigger phone call/SMS reminders via the cron system.

**Independent Test**: Say "add dinner with friends Saturday at 7pm" → verify event appears on Life calendar. Say "add urgent: dentist tomorrow 2pm" → verify event created + cron reminder job scheduled.

### Implementation for User Story 2

- [x] T016 [US2] Implement create_event(title, start_time, end_time, description, location) in bot/google_calendar.py. Always creates on Life calendar. Default end_time to start_time + 1 hour if not provided. Use CRON_TIMEZONE. Return created event dict (including id for future reference). Reject if calendar="work" → return error string
- [x] T017 [US2] Implement _schedule_urgent_reminder(event_id, event_title, event_start, reminder_minutes, reminder_channel) in bot/google_calendar.py. Import cron.create_job(). Create one-shot cron job: schedule_type="at", schedule_value=ISO datetime of (event_start - reminder_minutes), payload=cascade instruction message for Claude (try phone_call first, fallback to sms, then Discord), delivery_channel="discord". Store mapping of event_id → cron_job_id in the cron job context field for later cleanup
- [x] T018 [US2] Extend run_google_calendar() in bot/tools.py for action="create". Validate required params (title, start_time). Call create_event(). If urgent=true: call _schedule_urgent_reminder() with reminder_minutes (default 15) and reminder_channel (default "phone_call"). Return confirmation string with event details and reminder info

### Tests for User Story 2

- [x] T019 [P] [US2] Add create_event() tests to tests/test_google_calendar.py. Mock Google API insert. Test: successful creation, default end_time (1 hour), work calendar rejection, timezone handling
- [x] T020 [P] [US2] Add _schedule_urgent_reminder() tests to tests/test_google_calendar.py. Mock cron.create_job(). Test: correct schedule_type="at", correct fire time calculation, default 15 min offset, custom offset, phone_call default channel

**Checkpoint**: User Story 2 fully functional. Bot creates events on Life calendar. Urgent events get cron-based reminders with cascade fallback.

---

## Phase 5: User Story 3 - Daily Schedule Summary via Scheduled Delivery (Priority: P3)

**Goal**: Users can set up recurring daily briefings that deliver merged calendar summaries each morning via Discord. Urgent events highlighted.

**Independent Test**: Set up a cron job via "send me my schedule every morning at 8am" → verify the cron job is created and, when fired, delivers a formatted calendar summary.

### Implementation for User Story 3

- [x] T021 [US3] No new code needed for basic flow — the existing cron system + google_calendar list action already supports this. Claude uses cron_create tool to schedule a recurring job whose payload is "List my calendar events for today using google_calendar tool". Verify this works by testing the integration manually
- [ ] T022 [US3] Update format_events() in bot/google_calendar.py to visually distinguish urgent events with 🚨 marker and display the scheduled reminder time (e.g., "🚨 14:00 - 15:00 [Life] Dentist (reminder: phone call at 13:45)"). This requires looking up associated cron jobs by event_id in the context field

**Checkpoint**: User Story 3 functional. Daily briefings deliver merged calendar view with urgent event highlighting.

---

## Phase 6: User Story 4 - Modify or Delete Personal Events (Priority: P4)

**Goal**: Users can update or cancel Life calendar events. Work calendar events are read-only. Reminder cron jobs are cleaned up when events are deleted or rescheduled.

**Independent Test**: Say "cancel my dinner on Friday" → verify event deleted from Life calendar and any associated reminder cron job is also deleted.

### Implementation for User Story 4

- [x] T023 [US4] Implement update_event(event_id, updates) in bot/google_calendar.py. Only operates on Life calendar events. Accept updates dict with optional keys: title, start_time, end_time, description, location. Call Google API events().patch(). If start_time changes and event has an associated reminder: delete old cron job and create new one with updated time
- [x] T024 [US4] Implement delete_event(event_id) in bot/google_calendar.py. Only operates on Life calendar events. Call Google API events().delete(). Clean up associated reminder cron job if one exists (search cron_jobs by event_id in context field). Return confirmation string
- [x] T025 [US4] Implement _find_reminder_job(event_id) helper in bot/google_calendar.py. Search cron_jobs table for jobs whose context field contains the given event_id. Return job_id or None. Used by update and delete to manage reminder lifecycle
- [x] T026 [US4] Extend run_google_calendar() in bot/tools.py for action="update" and action="delete". For update: validate event_id and updates params, call update_event(), return confirmation. For delete: validate event_id, call delete_event(), return confirmation. Both reject work calendar operations with error message

### Tests for User Story 4

- [x] T027 [P] [US4] Add update_event() and delete_event() tests to tests/test_google_calendar.py. Mock Google API patch/delete. Test: successful update, successful delete, work calendar rejection, reminder cleanup on time change, reminder cleanup on delete
- [x] T028 [P] [US4] Add _find_reminder_job() tests to tests/test_google_calendar.py. Mock cron DB. Test: found by event_id in context, not found returns None

**Checkpoint**: All user stories functional. Full CRUD on Life calendar, read-only Work calendar, urgent reminders with lifecycle management.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Error handling, edge cases, and validation across all stories

- [x] T029 Add graceful error handling for Google API errors in bot/google_calendar.py: rate limit (429) → "Please try again in a moment", auth failure (401) → attempt refresh then re-try, network error → "Google Calendar service is unreachable"
- [x] T030 [P] Run full test suite: pytest --cov=bot --cov-report=term-missing. Verify coverage stays above 60% threshold. Add missing tests if needed
- [ ] T031 [P] Validate quickstart.md by walking through setup steps on a clean environment. Update any outdated instructions
- [ ] T032 Run the bot end-to-end and test all 4 user stories manually against real Google Calendar

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Phase 2 completion
  - US1 (Phase 3): No dependencies on other stories — **implement first as MVP**
  - US2 (Phase 4): No dependencies on other stories (creates events independently)
  - US3 (Phase 5): Depends on US1 (uses list_events for summary) and existing cron system
  - US4 (Phase 6): No dependencies on other stories (update/delete operates on existing events)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **US1 (P1)**: Foundation only → Start after Phase 2
- **US2 (P2)**: Foundation only → Can run in parallel with US1
- **US3 (P3)**: Requires US1 list_events + format_events → Start after Phase 3
- **US4 (P4)**: Foundation only → Can run in parallel with US1/US2

### Within Each User Story

- Implementation tasks before tests (tests validate implementation)
- Core API wrapper before tool integration
- Tool definition before dispatcher integration

### Parallel Opportunities

- T001 + T002: Dependencies can be added in parallel
- T003 + T004: Config and .env.example are independent files
- T014 + T015: Test files are independent
- T019 + T020: Test files are independent
- T027 + T028: Test files are independent
- US1 + US2 + US4: Can be implemented in parallel after Phase 2 (different functions in same files, but logically independent)

---

## Parallel Example: User Story 1

```bash
# After Phase 2 foundation is complete:

# Step 1: Implement core calendar functions (sequential in same file):
Task T009: "list_events() in bot/google_calendar.py"
Task T010: "format_events() in bot/google_calendar.py"

# Step 2: Integrate with tool system:
Task T011: "GOOGLE_CALENDAR_TOOL definition in bot/tools.py"
Task T012: "run_google_calendar() handler in bot/tools.py"
Task T013: "handle_tool_call() dispatcher in bot/tools.py"

# Step 3: Tests (parallel, different files):
Task T014: "tests/test_google_calendar.py"  ← can run in parallel
Task T015: "tests/test_tools.py"            ← can run in parallel
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 2: Foundational — OAuth + Calendar client (T005-T008)
3. Complete Phase 3: User Story 1 — list events (T009-T015)
4. **STOP and VALIDATE**: Ask "what's on my calendar today?" and verify merged view
5. Deploy if ready — core value is already delivered

### Incremental Delivery

1. Setup + Foundational → Google Calendar connected
2. Add US1 → Merged schedule view → **Deploy (MVP!)**
3. Add US2 → Event creation + urgent reminders → Deploy
4. Add US3 → Daily briefings → Deploy
5. Add US4 → Event modification/deletion → Deploy
6. Polish → Error handling, tests, validation → Final deploy

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- The google_calendar tool is a single tool with action parameter — all actions share the same tool definition (T011) but have separate handler logic
- Urgent reminders use existing cron system — no new scheduler infrastructure needed
- All Google API calls are mocked in tests — tests run offline
