"""Tests for Discord channel adapter helpers."""

from unittest.mock import MagicMock

from bot.channel.discord import _extract_image_urls


def _make_message(attachments=None, embeds=None):
    msg = MagicMock()
    msg.attachments = attachments or []
    msg.embeds = embeds or []
    return msg


class TestExtractImageUrls:
    def test_image_attachment(self):
        att = MagicMock()
        att.content_type = "image/png"
        att.url = "https://cdn.discord.com/test.png"
        msg = _make_message(attachments=[att])
        urls = _extract_image_urls(msg)
        assert urls == ["https://cdn.discord.com/test.png"]

    def test_non_image_attachment_ignored(self):
        att = MagicMock()
        att.content_type = "application/pdf"
        att.url = "https://cdn.discord.com/test.pdf"
        msg = _make_message(attachments=[att])
        urls = _extract_image_urls(msg)
        assert urls == []

    def test_embed_image(self):
        embed = MagicMock()
        embed.image = MagicMock()
        embed.image.url = "https://embed.img/photo.jpg"
        embed.thumbnail = MagicMock()
        embed.thumbnail.url = None
        msg = _make_message(embeds=[embed])
        urls = _extract_image_urls(msg)
        assert "https://embed.img/photo.jpg" in urls

    def test_no_images(self):
        msg = _make_message()
        urls = _extract_image_urls(msg)
        assert urls == []
