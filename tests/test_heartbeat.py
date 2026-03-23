"""Tests for bot.heartbeat — token stripping, content checks, active hours."""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from bot.heartbeat import (
    HeartbeatRunner,
    is_heartbeat_content_empty,
    is_within_active_hours,
    read_heartbeat_file,
    strip_heartbeat_token,
)


# ── is_heartbeat_content_empty ───────────────────────────────────────────────

class TestContentEmpty:
    def test_empty_string(self):
        assert is_heartbeat_content_empty("") is True

    def test_only_headers(self):
        assert is_heartbeat_content_empty("# Heartbeat\n## Sub") is True

    def test_headers_and_blank_lines(self):
        assert is_heartbeat_content_empty("# Heartbeat\n\n  \n## Sub\n") is True

    def test_empty_list_items(self):
        assert is_heartbeat_content_empty("- \n* \n+ ") is True

    def test_empty_checkbox_items(self):
        assert is_heartbeat_content_empty("- [ ] \n- [x] ") is True

    def test_actionable_content(self):
        assert is_heartbeat_content_empty("# Heartbeat\n- Check inbox") is False

    def test_text_only(self):
        assert is_heartbeat_content_empty("Check inbox for urgent messages") is False


# ── read_heartbeat_file ──────────────────────────────────────────────────────

class TestReadHeartbeatFile:
    def test_missing_file(self, tmp_path):
        assert read_heartbeat_file(tmp_path) is None

    def test_empty_file(self, tmp_path):
        (tmp_path / "HEARTBEAT.md").write_text("")
        assert read_heartbeat_file(tmp_path) is None

    def test_only_headers(self, tmp_path):
        (tmp_path / "HEARTBEAT.md").write_text("# Heartbeat\n\n## Section\n")
        assert read_heartbeat_file(tmp_path) is None

    def test_with_content(self, tmp_path):
        content = "# Heartbeat\n- Check inbox"
        (tmp_path / "HEARTBEAT.md").write_text(content)
        result = read_heartbeat_file(tmp_path)
        assert result is not None
        assert "Check inbox" in result


# ── strip_heartbeat_token ────────────────────────────────────────────────────

class TestStripToken:
    def test_exact_token(self):
        skip, text, did = strip_heartbeat_token("HEARTBEAT_OK")
        assert skip is True
        assert text == ""
        assert did is True

    def test_token_with_trailing_punct(self):
        skip, text, did = strip_heartbeat_token("HEARTBEAT_OK!!!")
        assert skip is True
        assert text == ""
        assert did is True

    def test_token_at_start(self):
        skip, text, did = strip_heartbeat_token("HEARTBEAT_OK All good nothing to do")
        assert did is True
        assert "All good" in text

    def test_token_at_end(self):
        skip, text, did = strip_heartbeat_token("Nothing to report. HEARTBEAT_OK")
        assert did is True

    def test_short_text_after_token_skips(self):
        skip, text, did = strip_heartbeat_token("HEARTBEAT_OK fine")
        assert skip is True  # "fine" is ≤300 chars
        assert did is True

    def test_long_text_after_token_delivers(self):
        long_text = "A" * 400
        skip, text, did = strip_heartbeat_token(f"HEARTBEAT_OK {long_text}")
        assert skip is False  # >300 chars
        assert did is True
        assert long_text in text

    def test_no_token(self):
        skip, text, did = strip_heartbeat_token("You have 3 urgent emails")
        assert skip is False
        assert did is False
        assert "urgent" in text

    def test_html_wrapped_token(self):
        skip, text, did = strip_heartbeat_token("<b>HEARTBEAT_OK</b>")
        assert did is True
        assert skip is True

    def test_case_insensitive(self):
        skip, text, did = strip_heartbeat_token("heartbeat_ok")
        assert did is True
        assert skip is True


# ── is_within_active_hours ───────────────────────────────────────────────────

class TestActiveHours:
    def test_no_config(self):
        assert is_within_active_hours(None, None) is True

    def test_same_start_end_disabled(self):
        assert is_within_active_hours("09:00", "09:00") is False

    def test_invalid_format_fail_open(self):
        assert is_within_active_hours("abc", "def") is True

    @patch("bot.heartbeat.datetime")
    def test_within_range(self, mock_dt):
        from datetime import datetime as real_dt
        mock_now = real_dt(2026, 3, 23, 14, 30)  # 14:30
        mock_dt.now.return_value = mock_now
        assert is_within_active_hours("09:00", "18:00") is True

    @patch("bot.heartbeat.datetime")
    def test_outside_range(self, mock_dt):
        from datetime import datetime as real_dt
        mock_now = real_dt(2026, 3, 23, 7, 0)  # 07:00
        mock_dt.now.return_value = mock_now
        assert is_within_active_hours("09:00", "18:00") is False

    @patch("bot.heartbeat.datetime")
    def test_midnight_wrap_inside(self, mock_dt):
        from datetime import datetime as real_dt
        mock_now = real_dt(2026, 3, 23, 23, 0)  # 23:00
        mock_dt.now.return_value = mock_now
        assert is_within_active_hours("22:00", "06:00") is True

    @patch("bot.heartbeat.datetime")
    def test_midnight_wrap_outside(self, mock_dt):
        from datetime import datetime as real_dt
        mock_now = real_dt(2026, 3, 23, 12, 0)  # 12:00
        mock_dt.now.return_value = mock_now
        assert is_within_active_hours("22:00", "06:00") is False


# ── HeartbeatRunner ──────────────────────────────────────────────────────────

class TestHeartbeatRunner:
    @pytest.fixture
    def mock_agent(self, tmp_path):
        """Create a mock agent with workspace dir."""
        agent = type("Agent", (), {
            "name": "test",
            "workspace_dir": tmp_path,
            "system_prompt": "You are helpful.",
            "memory_dir": tmp_path / "memory",
            "session_mgr": None,
        })()
        (tmp_path / "HEARTBEAT.md").write_text("# Heartbeat\n- Check inbox\n")
        return agent

    @pytest.mark.asyncio
    async def test_skip_empty_heartbeat_file(self, tmp_path):
        agent = type("Agent", (), {
            "name": "test",
            "workspace_dir": tmp_path,
        })()
        deliver = AsyncMock()
        runner = HeartbeatRunner(agent=agent, deliver_fn=deliver)
        result = await runner.run_once()
        assert result == "skipped:empty-heartbeat-file"
        deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_ok_empty_response(self, mock_agent):
        deliver = AsyncMock()
        runner = HeartbeatRunner(agent=mock_agent, deliver_fn=deliver)

        with patch("bot.llm.reply", new_callable=AsyncMock, return_value="HEARTBEAT_OK"):
            result = await runner.run_once()

        assert result == "ok-empty"
        deliver.assert_not_called()

    @pytest.mark.asyncio
    async def test_delivers_alert(self, mock_agent):
        deliver = AsyncMock()
        runner = HeartbeatRunner(agent=mock_agent, deliver_fn=deliver)

        alert = "You have 3 urgent emails that need attention right now."
        with patch("bot.llm.reply", new_callable=AsyncMock, return_value=alert):
            result = await runner.run_once()

        assert result == "sent"
        deliver.assert_called_once_with(alert)

    @pytest.mark.asyncio
    async def test_delivers_stripped_alert(self, mock_agent):
        deliver = AsyncMock()
        runner = HeartbeatRunner(agent=mock_agent, deliver_fn=deliver)

        long_alert = "A" * 400
        reply = f"HEARTBEAT_OK {long_alert}"
        with patch("bot.llm.reply", new_callable=AsyncMock, return_value=reply):
            result = await runner.run_once()

        assert result == "sent"
        deliver.assert_called_once()
        delivered_text = deliver.call_args[0][0]
        assert long_alert in delivered_text

    @pytest.mark.asyncio
    async def test_dedup_within_24h(self, mock_agent):
        deliver = AsyncMock()
        runner = HeartbeatRunner(agent=mock_agent, deliver_fn=deliver)

        alert = "You have 3 urgent emails."
        with patch("bot.llm.reply", new_callable=AsyncMock, return_value=alert):
            r1 = await runner.run_once()
            r2 = await runner.run_once()

        assert r1 == "sent"
        assert r2 == "skipped:duplicate"
        assert deliver.call_count == 1

    @pytest.mark.asyncio
    async def test_skip_outside_active_hours(self, mock_agent):
        deliver = AsyncMock()
        runner = HeartbeatRunner(
            agent=mock_agent,
            deliver_fn=deliver,
            active_hours_start="09:00",
            active_hours_end="09:00",  # same = disabled
        )
        result = await runner.run_once()
        assert result == "skipped:active-hours"
