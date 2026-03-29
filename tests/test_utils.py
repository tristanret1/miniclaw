"""Tests for bot.utils — session_keys and discord utilities."""

import asyncio
import time
from unittest.mock import AsyncMock

from bot.utils.session_keys import (
    discord_key,
    greeting_key,
    cron_key,
    heartbeat_key,
    voice_key,
    imessage_key,
    sms_key,
)
from bot.utils.discord import send_chunks


class TestSessionKeys:
    def test_discord_key(self):
        assert discord_key(123, 456) == "123:456"

    def test_greeting_key(self):
        assert greeting_key(789) == "789:system"
        assert greeting_key("chan") == "chan:system"

    def test_cron_key_shared(self):
        assert cron_key("job1") == "cron:job1"

    def test_cron_key_isolated(self):
        k = cron_key("job1", isolated=True)
        assert k.startswith("cron:job1:")
        # Should contain a timestamp
        ts_part = k.split(":")[-1]
        assert ts_part.isdigit()

    def test_heartbeat_key_shared(self):
        assert heartbeat_key("ch1") == "ch1:heartbeat"

    def test_heartbeat_key_isolated(self):
        k = heartbeat_key("ch1", isolated=True)
        assert k.startswith("ch1:heartbeat:")
        ts_part = k.split(":")[-1]
        assert ts_part.isdigit()

    def test_voice_key(self):
        assert voice_key() == "voice:local"

    def test_imessage_key_plain(self):
        assert imessage_key("+1234567890") == "imessage:+1234567890"

    def test_imessage_key_strips_service_prefix(self):
        assert imessage_key("imessage:user@example.com") == "imessage:user@example.com"

    def test_imessage_key_normalizes_case(self):
        assert imessage_key("USER@Example.COM") == "imessage:user@example.com"

    def test_imessage_key_strips_whitespace(self):
        assert imessage_key("  user@ex.com  ") == "imessage:user@ex.com"

    def test_sms_key(self):
        assert sms_key("+1234567890") == "sms:+1234567890"


class TestSendChunks:
    async def test_short_message_single_send(self):
        channel = AsyncMock()
        await send_chunks(channel, "hello", chunk_size=2000)
        channel.send.assert_called_once_with("hello")

    async def test_long_message_split(self):
        channel = AsyncMock()
        text = "a" * 5
        await send_chunks(channel, text, chunk_size=2)
        assert channel.send.call_count == 3
        calls = [c.args[0] for c in channel.send.call_args_list]
        assert calls == ["aa", "aa", "a"]
