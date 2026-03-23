"""Tests for bot.client — Discord event handling helpers."""

from unittest.mock import MagicMock, AsyncMock, patch

from bot.client import (
    _extract_image_urls,
    should_auto_reply,
)


def _make_message(
    content="",
    author_id=123,
    guild=True,
    bot_user_id=999,
    mentions=None,
    attachments=None,
    embeds=None,
):
    """Build a mock discord.Message."""
    msg = MagicMock()
    msg.content = content
    msg.author = MagicMock()
    msg.author.id = author_id
    msg.guild = MagicMock() if guild else None
    msg.channel = MagicMock()
    msg.channel.id = 456
    msg.mentions = mentions or []
    msg.attachments = attachments or []
    msg.embeds = embeds or []
    return msg, bot_user_id


class TestExtractImageUrls:
    def test_image_attachment(self):
        att = MagicMock()
        att.content_type = "image/png"
        att.url = "https://cdn.discord.com/test.png"
        msg, _ = _make_message(attachments=[att])
        urls = _extract_image_urls(msg)
        assert urls == ["https://cdn.discord.com/test.png"]

    def test_non_image_attachment_ignored(self):
        att = MagicMock()
        att.content_type = "application/pdf"
        att.url = "https://cdn.discord.com/test.pdf"
        msg, _ = _make_message(attachments=[att])
        urls = _extract_image_urls(msg)
        assert urls == []

    def test_embed_image(self):
        embed = MagicMock()
        embed.image = MagicMock()
        embed.image.url = "https://embed.img/photo.jpg"
        embed.thumbnail = MagicMock()
        embed.thumbnail.url = None
        msg, _ = _make_message(embeds=[embed])
        urls = _extract_image_urls(msg)
        assert "https://embed.img/photo.jpg" in urls

    def test_no_images(self):
        msg, _ = _make_message()
        urls = _extract_image_urls(msg)
        assert urls == []


class TestShouldAutoReply:
    def test_disabled(self, monkeypatch):
        monkeypatch.setattr("bot.client.AUTO_REPLY_ENABLED", False)
        msg, _ = _make_message(guild=True)
        bot_user = MagicMock()
        assert should_auto_reply(msg, bot_user) is False

    def test_dm_rejected(self, monkeypatch):
        monkeypatch.setattr("bot.client.AUTO_REPLY_ENABLED", True)
        msg, _ = _make_message(guild=False)
        bot_user = MagicMock()
        assert should_auto_reply(msg, bot_user) is False

    def test_mention_rejected(self, monkeypatch):
        monkeypatch.setattr("bot.client.AUTO_REPLY_ENABLED", True)
        bot_user = MagicMock()
        msg, _ = _make_message(guild=True, mentions=[bot_user])
        assert should_auto_reply(msg, bot_user) is False
