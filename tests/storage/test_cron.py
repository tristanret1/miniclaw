"""Tests for bot.services.cron — schedule computation, backoff, and helpers."""

import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from bot.services.cron import (
    CronJob,
    _parse_duration_seconds,
    compute_next_run,
    _backoff_delay,
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
