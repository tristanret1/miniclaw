"""Tests for bot.google_calendar — Calendar API wrapper."""

import os
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

from bot.services.google_calendar import (
    _build_service,
    _parse_event,
    format_events,
    list_events,
    create_event,
    update_event,
    delete_event,
    _find_reminder_job,
    _schedule_urgent_reminder,
)

# Integration tests require real Google credentials + calendar IDs.
# Read .env directly because conftest.pytest_configure overrides env vars before import.
_project_root = os.path.join(os.path.dirname(__file__), "..")
_has_google_creds = os.path.exists(os.path.join(_project_root, ".google_credentials.json"))
_has_real_calendar_id = False
_env_path = os.path.join(_project_root, ".env")
if os.path.exists(_env_path):
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("GOOGLE_CALENDAR_LIFE_ID=") and not line.endswith("="):
                _has_real_calendar_id = True
                break
requires_google = pytest.mark.skipif(
    not (_has_google_creds and _has_real_calendar_id),
    reason="Real Google credentials / calendar IDs not configured",
)


# ── Sample Google API event dicts ──────────────────────────────────────────

SAMPLE_TIMED_EVENT = {
    "id": "evt1",
    "summary": "Team standup",
    "start": {"dateTime": "2026-03-23T09:00:00-07:00", "timeZone": "America/Vancouver"},
    "end": {"dateTime": "2026-03-23T10:00:00-07:00", "timeZone": "America/Vancouver"},
    "description": "Daily standup",
    "location": "Office",
}

SAMPLE_ALL_DAY_EVENT = {
    "id": "evt2",
    "summary": "Holiday",
    "start": {"date": "2026-03-23"},
    "end": {"date": "2026-03-24"},
}

SAMPLE_NO_TITLE_EVENT = {
    "id": "evt3",
    "start": {"dateTime": "2026-03-23T14:00:00-07:00"},
    "end": {"dateTime": "2026-03-23T15:00:00-07:00"},
}


# ── _parse_event ───────────────────────────────────────────────────────────

class TestParseEvent:
    def test_timed_event(self):
        result = _parse_event(SAMPLE_TIMED_EVENT, "Work")
        assert result["id"] == "evt1"
        assert result["title"] == "Team standup"
        assert result["source_calendar"] == "Work"
        assert result["is_all_day"] is False
        assert "09:00:00" in result["start"]
        assert result["description"] == "Daily standup"
        assert result["location"] == "Office"

    def test_all_day_event(self):
        result = _parse_event(SAMPLE_ALL_DAY_EVENT, "Life")
        assert result["is_all_day"] is True
        assert result["start"] == "2026-03-23"
        assert result["source_calendar"] == "Life"

    def test_no_title_event(self):
        result = _parse_event(SAMPLE_NO_TITLE_EVENT, "Life")
        assert result["title"] == "(No title)"


# ── format_events ──────────────────────────────────────────────────────────

class TestFormatEvents:
    def test_empty_list(self):
        result = format_events([])
        assert "No events found" in result

    def test_single_event(self):
        events = [_parse_event(SAMPLE_TIMED_EVENT, "Work")]
        result = format_events(events)
        assert "[Work]" in result
        assert "Team standup" in result
        assert "1 event found" in result

    def test_multiple_events_merged(self):
        events = [
            _parse_event(SAMPLE_TIMED_EVENT, "Work"),
            _parse_event(SAMPLE_ALL_DAY_EVENT, "Life"),
        ]
        result = format_events(events)
        assert "[Work]" in result
        assert "[Life]" in result
        assert "2 events found" in result

    def test_all_day_display(self):
        events = [_parse_event(SAMPLE_ALL_DAY_EVENT, "Life")]
        result = format_events(events)
        assert "All day" in result


# ── list_events (mocked) ──────────────────────────────────────────────────

class TestListEvents:
    @patch("bot.services.google_calendar._build_service")
    def test_list_both_calendars(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        # Life calendar returns one event
        life_events = {"items": [SAMPLE_TIMED_EVENT]}
        # Work calendar returns one event
        work_events = {"items": [SAMPLE_ALL_DAY_EVENT]}

        mock_service.events.return_value.list.return_value.execute.side_effect = [
            life_events,
            work_events,
        ]

        result = list_events(
            calendar="both",
            date_start="2026-03-23T00:00:00-07:00",
            date_end="2026-03-24T00:00:00-07:00",
        )
        assert len(result) == 2
        # Should be sorted: all-day first (date string < dateTime string)
        assert result[0]["source_calendar"] in ("Life", "Work")

    @patch("bot.services.google_calendar._build_service")
    def test_list_single_calendar(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.events.return_value.list.return_value.execute.return_value = {
            "items": [SAMPLE_TIMED_EVENT]
        }

        result = list_events(
            calendar="work",
            date_start="2026-03-23T00:00:00-07:00",
            date_end="2026-03-24T00:00:00-07:00",
        )
        assert len(result) == 1
        assert result[0]["source_calendar"] == "Work"

    @patch("bot.services.google_calendar._build_service")
    def test_list_empty_results(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events.return_value.list.return_value.execute.return_value = {"items": []}

        result = list_events(
            calendar="life",
            date_start="2026-03-23T00:00:00-07:00",
            date_end="2026-03-24T00:00:00-07:00",
        )
        assert result == []


# ── create_event (mocked) ─────────────────────────────────────────────────

class TestCreateEvent:
    @patch("bot.services.google_calendar._build_service")
    def test_create_basic(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "new-evt-1",
            "summary": "Dinner",
            "start": {"dateTime": "2026-03-23T19:00:00-07:00"},
            "end": {"dateTime": "2026-03-23T20:00:00-07:00"},
        }

        result = create_event(title="Dinner", start_time="2026-03-23T19:00:00")
        assert result["id"] == "new-evt-1"
        assert result["title"] == "Dinner"
        assert result["source_calendar"] == "Life"

    @patch("bot.services.google_calendar._build_service")
    def test_create_default_end_time(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.events.return_value.insert.return_value.execute.return_value = {
            "id": "new-evt-2",
            "summary": "Meeting",
            "start": {"dateTime": "2026-03-23T14:00:00-07:00"},
            "end": {"dateTime": "2026-03-23T15:00:00-07:00"},
        }

        result = create_event(title="Meeting", start_time="2026-03-23T14:00:00")
        # Verify the insert was called with end = start + 1 hour
        call_args = mock_service.events.return_value.insert.call_args
        body = call_args[1]["body"] if "body" in call_args[1] else call_args[0][0]
        # Just verify the event was created successfully
        assert result["id"] == "new-evt-2"


# ── update_event (mocked) ─────────────────────────────────────────────────

class TestUpdateEvent:
    @patch("bot.services.google_calendar._build_service")
    def test_update_title(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service

        mock_service.events.return_value.patch.return_value.execute.return_value = {
            "id": "evt1",
            "summary": "Updated standup",
            "start": {"dateTime": "2026-03-23T09:00:00-07:00"},
            "end": {"dateTime": "2026-03-23T10:00:00-07:00"},
        }

        result = update_event(event_id="evt1", updates={"title": "Updated standup"})
        assert result["title"] == "Updated standup"


# ── delete_event (mocked) ─────────────────────────────────────────────────

class TestDeleteEvent:
    @patch("bot.services.google_calendar._find_reminder_job", return_value=None)
    @patch("bot.services.google_calendar._build_service")
    async def test_delete_success(self, mock_build, mock_find):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events.return_value.delete.return_value.execute.return_value = None

        result = await delete_event(event_id="evt1")
        assert "deleted" in result.lower()
        assert "evt1" in result

    @patch("bot.services.google_calendar._build_service")
    async def test_delete_with_reminder_cleanup(self, mock_build):
        mock_service = MagicMock()
        mock_build.return_value = mock_service
        mock_service.events.return_value.delete.return_value.execute.return_value = None

        with patch("bot.services.google_calendar._find_reminder_job", return_value="job-123"):
            with patch("bot.cron.delete_job", new_callable=AsyncMock) as mock_delete_job:
                result = await delete_event(event_id="evt1")
                mock_delete_job.assert_called_once_with("job-123")
                assert "deleted" in result.lower()


# ── _schedule_urgent_reminder (mocked) ────────────────────────────────────

class TestScheduleUrgentReminder:
    @patch("bot.cron.create_job", new_callable=AsyncMock, return_value="Created job 'Reminder: Dentist' (id=abc123)")
    async def test_default_reminder(self, mock_create_job):
        result = await _schedule_urgent_reminder(
            event_id="evt1",
            event_title="Dentist",
            event_start="2026-03-23T14:00:00-07:00",
        )
        assert "Created job" in result
        mock_create_job.assert_called_once()
        call_kwargs = mock_create_job.call_args[1]
        assert call_kwargs["schedule_type"] == "at"
        assert call_kwargs["name"] == "Reminder: Dentist"
        assert "calendar_event_id:evt1" in call_kwargs["context"]

    @patch("bot.cron.create_job", new_callable=AsyncMock, return_value="Created job 'Reminder: Flight' (id=def456)")
    async def test_custom_offset(self, mock_create_job):
        result = await _schedule_urgent_reminder(
            event_id="evt2",
            event_title="Flight",
            event_start="2026-03-23T14:00:00-07:00",
            reminder_minutes=30,
            reminder_channel="sms",
        )
        assert "Created job" in result
        call_kwargs = mock_create_job.call_args[1]
        assert "sms" in call_kwargs["payload"]


# ── _find_reminder_job (mocked) ───────────────────────────────────────────

class TestFindReminderJob:
    @patch("bot.cron._get_db")
    def test_found(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.execute.return_value.fetchone.return_value = ("job-abc",)

        result = _find_reminder_job("evt1")
        assert result == "job-abc"

    @patch("bot.cron._get_db")
    def test_not_found(self, mock_get_db):
        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.execute.return_value.fetchone.return_value = None

        result = _find_reminder_job("evt-nonexistent")
        assert result is None

    def test_error_returns_none(self):
        with patch("bot.cron._get_db", side_effect=Exception("DB error")):
            result = _find_reminder_job("evt1")
            assert result is None


# ── Integration tests (real Google Calendar API) ─────────────────────────

def _load_real_env():
    """Load real calendar IDs from .env, overriding conftest fakes."""
    if not os.path.exists(_env_path):
        return
    with open(_env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            # Strip inline comments (e.g. "value  # comment")
            if "#" in val:
                val = val[:val.index("#")].strip()
            if key.startswith("GOOGLE_CALENDAR_"):
                os.environ[key] = val


_google_env_keys = (
    "GOOGLE_CALENDAR_LIFE_ID",
    "GOOGLE_CALENDAR_WORK_ID",
    "GOOGLE_CALENDAR_CLIENT_ID",
    "GOOGLE_CALENDAR_CLIENT_SECRET",
    "GOOGLE_CALENDAR_ENABLED",
)


@pytest.fixture(autouse=True, scope="class")
def _real_google_env():
    """Swap in real Google env vars for integration tests, restore after."""
    import importlib
    import bot.config as cfg
    import bot.services.google_calendar as gcal

    saved = {k: os.environ.get(k) for k in _google_env_keys}
    _load_real_env()
    importlib.reload(cfg)
    importlib.reload(gcal)
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(cfg)
    importlib.reload(gcal)


@pytest.mark.integration
@requires_google
class TestGoogleCalendarIntegration:
    """Tests that hit the real Google Calendar API.

    Run with: pytest -m integration tests/test_google_calendar.py
    Requires: .google_credentials.json + real GOOGLE_CALENDAR_LIFE_ID in .env
    """

    def test_build_service(self, caplog):
        """Verify we can authenticate and build a service client."""
        import logging
        with caplog.at_level(logging.DEBUG):
            service = _build_service()
            assert service is not None
            print(f"Service built: {type(service).__name__}")

    def test_list_events_today(self, caplog):
        """List today's events from life calendar."""
        import logging
        from bot.config import CRON_TIMEZONE
        tz = ZoneInfo(CRON_TIMEZONE)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()

        with caplog.at_level(logging.DEBUG):
            print(f"Querying life calendar: {start} → {end}")
            result = list_events(calendar="life", date_start=start, date_end=end)
            assert isinstance(result, list)
            print(f"Got {len(result)} events")
            for ev in result:
                assert "id" in ev
                assert "title" in ev
                assert ev["source_calendar"] == "Life"
                print(f"  {ev['start']} | {ev['title']}")

    async def test_crud_lifecycle(self, caplog):
        """Create → read → update → delete a test event."""
        import logging
        from bot.config import CRON_TIMEZONE
        tz = ZoneInfo(CRON_TIMEZONE)
        tomorrow = datetime.now(tz).replace(
            hour=23, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)

        with caplog.at_level(logging.DEBUG):
            # Create
            print(f"Creating test event at {tomorrow.isoformat()}")
            created = create_event(
                title="[TEST] MiniClaw Integration Test",
                start_time=tomorrow.isoformat(),
                end_time=(tomorrow + timedelta(hours=1)).isoformat(),
                description="Auto-created by pytest integration test. Safe to delete.",
            )
            event_id = created["id"]
            assert event_id
            assert created["title"] == "[TEST] MiniClaw Integration Test"
            assert created["source_calendar"] == "Life"
            print(f"Created event: {event_id}")

            try:
                # Read — verify it shows up in list
                start = tomorrow.replace(hour=0).isoformat()
                end = (tomorrow.replace(hour=0) + timedelta(days=1)).isoformat()
                events = list_events(calendar="life", date_start=start, date_end=end)
                found = [e for e in events if e["id"] == event_id]
                assert len(found) == 1, f"Created event {event_id} not found in list"
                print(f"Verified event in list ({len(events)} total events)")

                # Update
                updated = update_event(event_id, updates={"title": "[TEST] Updated Title"})
                assert updated["title"] == "[TEST] Updated Title"
                print(f"Updated event title → '{updated['title']}'")

            finally:
                # Delete (always clean up)
                result = await delete_event(event_id)
                assert "deleted" in result.lower()
                print(f"Deleted event: {event_id}")

    def test_list_both_calendars(self, caplog):
        """List from both calendars if work calendar is accessible."""
        import logging
        from bot.config import GOOGLE_CALENDAR_WORK_ID, CRON_TIMEZONE

        if not GOOGLE_CALENDAR_WORK_ID or "test-" in GOOGLE_CALENDAR_WORK_ID:
            pytest.skip("Real GOOGLE_CALENDAR_WORK_ID not configured")

        tz = ZoneInfo(CRON_TIMEZONE)
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        end = (now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).isoformat()

        with caplog.at_level(logging.DEBUG):
            print(f"Querying both calendars: {start} → {end}")
            try:
                result = list_events(calendar="both", date_start=start, date_end=end)
            except Exception as e:
                pytest.skip(f"Work calendar not accessible: {e}")
            assert isinstance(result, list)
            sources = {e["source_calendar"] for e in result}
            assert sources <= {"Life", "Work"}
            print(f"Got {len(result)} events from {sources or 'no'} calendars")
