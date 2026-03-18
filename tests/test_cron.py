"""Tests for bot.cron — schedule computation, CRUD, and job lifecycle."""

import sqlite3
import time
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from bot.cron import (
    CronJob,
    _parse_duration_seconds,
    compute_next_run,
    _backoff_delay,
    _init_db,
    _row_to_job,
    create_job,
    list_jobs,
    delete_job,
)


class TestParseDuration:
    def test_minutes(self):
        assert _parse_duration_seconds("30m") == 1800.0

    def test_hours(self):
        assert _parse_duration_seconds("2h") == 7200.0

    def test_days(self):
        assert _parse_duration_seconds("1d") == 86400.0

    def test_combined(self):
        assert _parse_duration_seconds("1d12h") == 86400 + 43200

    def test_seconds(self):
        assert _parse_duration_seconds("45s") == 45.0

    def test_complex(self):
        assert _parse_duration_seconds("1d2h30m15s") == 86400 + 7200 + 1800 + 15

    def test_invalid(self):
        with pytest.raises(ValueError):
            _parse_duration_seconds("invalid")

    def test_empty_zero(self):
        with pytest.raises(ValueError):
            _parse_duration_seconds("")


class TestComputeNextRun:
    def test_every_interval(self):
        now = time.time()
        result = compute_next_run("every", "30m", "UTC", after=now)
        assert abs(result - (now + 1800)) < 1.0

    def test_cron_expression(self):
        # "0 8 * * *" = daily at 08:00
        now = time.time()
        result = compute_next_run("cron", "0 8 * * *", "UTC", after=now)
        assert result > now

    def test_at_relative(self):
        now = time.time()
        result = compute_next_run("at", "+20m", "UTC")
        assert abs(result - (now + 1200)) < 2.0

    def test_at_absolute(self):
        tz = "UTC"
        future = datetime(2030, 1, 1, 12, 0, tzinfo=ZoneInfo(tz))
        result = compute_next_run("at", future.isoformat(), tz)
        assert abs(result - future.timestamp()) < 1.0

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="Unknown schedule_type"):
            compute_next_run("bogus", "30m", "UTC")


class TestBackoffDelay:
    def test_first_error(self):
        assert _backoff_delay(1) == 30

    def test_second_error(self):
        assert _backoff_delay(2) == 60

    def test_max_backoff(self):
        assert _backoff_delay(100) == 3600


class TestCronCRUD:
    """Test CRUD operations using a temporary database."""

    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path, monkeypatch):
        """Point cron DB to a temp path."""
        db_path = tmp_path / "cron.db"
        monkeypatch.setattr("bot.cron.DB_PATH", db_path)
        monkeypatch.setattr("bot.cron._db", None)
        monkeypatch.setattr("bot.cron._scheduler", None)

    def test_create_job(self):
        result = create_job(
            name="test-job",
            schedule_type="every",
            schedule_value="1h",
            payload="Hello",
            channel_id="123456",
        )
        assert "Created job" in result
        assert "test-job" in result

    def test_create_invalid_schedule_type(self):
        result = create_job(
            name="bad", schedule_type="bogus",
            schedule_value="1h", payload="hi", channel_id="123",
        )
        assert "Error" in result

    def test_create_invalid_schedule_value(self):
        result = create_job(
            name="bad", schedule_type="every",
            schedule_value="not-a-duration", payload="hi", channel_id="123",
        )
        assert "Error" in result

    def test_list_jobs_empty(self):
        result = list_jobs()
        assert "No scheduled jobs" in result

    def test_list_jobs_after_create(self):
        create_job(
            name="lister", schedule_type="every",
            schedule_value="30m", payload="hi", channel_id="123",
        )
        result = list_jobs()
        assert "lister" in result
        assert "every 30m" in result

    def test_delete_job_by_id(self):
        result = create_job(
            name="deleteme", schedule_type="every",
            schedule_value="1h", payload="hi", channel_id="123",
        )
        # Extract job ID from result
        job_id = result.split("id=")[1].split(")")[0]
        del_result = delete_job(job_id)
        assert "Deleted" in del_result
        assert list_jobs() == "No scheduled jobs."

    def test_delete_job_by_name(self):
        create_job(
            name="byname", schedule_type="every",
            schedule_value="1h", payload="hi", channel_id="123",
        )
        del_result = delete_job("byname")
        assert "Deleted" in del_result

    def test_delete_nonexistent(self):
        result = delete_job("nope")
        assert "No job found" in result

    def test_create_with_session_mode(self):
        result = create_job(
            name="persistent-job", schedule_type="every",
            schedule_value="1h", payload="hi", channel_id="123",
            session_mode="persistent",
        )
        assert "persistent" in result

    def test_create_at_relative(self):
        result = create_job(
            name="one-shot", schedule_type="at",
            schedule_value="+20m", payload="fire once", channel_id="123",
        )
        assert "Created job" in result
        assert "one-shot" in result

    def test_list_includes_disabled(self):
        create_job(
            name="disabled-test", schedule_type="at",
            schedule_value="+1m", payload="hi", channel_id="123",
        )
        # Manually disable the job
        from bot.cron import _get_db
        db = _get_db()
        db.execute("UPDATE cron_jobs SET enabled=0")
        db.commit()

        assert "No scheduled jobs" in list_jobs(include_disabled=False)
        assert "disabled-test" in list_jobs(include_disabled=True)
