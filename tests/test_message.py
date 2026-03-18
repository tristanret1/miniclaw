"""Tests for bot.message — type builders and text extraction."""

from bot.message import build_user_content, extract_text


class TestBuildUserContent:
    def test_text_only(self):
        result = build_user_content("hello")
        assert result == "hello"

    def test_no_images_none(self):
        result = build_user_content("hi", image_urls=None)
        assert result == "hi"

    def test_no_images_empty_list(self):
        result = build_user_content("hi", image_urls=[])
        assert result == "hi"

    def test_with_images(self):
        result = build_user_content("look at this", ["https://img.png"])
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["type"] == "image"
        assert result[0]["source"]["url"] == "https://img.png"
        assert result[1]["type"] == "text"
        assert result[1]["text"] == "look at this"

    def test_multiple_images(self):
        urls = ["https://a.png", "https://b.jpg"]
        result = build_user_content("caption", urls)
        assert len(result) == 3
        assert all(b["type"] == "image" for b in result[:2])
        assert result[2]["type"] == "text"

    def test_images_with_empty_text(self):
        result = build_user_content("", ["https://img.png"])
        assert isinstance(result, list)
        # No text block appended when text is empty
        assert all(b["type"] == "image" for b in result)

    def test_image_source_format(self):
        result = build_user_content("x", ["https://example.com/photo.jpg"])
        img = result[0]
        assert img["source"]["type"] == "url"
        assert img["source"]["url"] == "https://example.com/photo.jpg"


class TestExtractText:
    def test_from_string(self):
        assert extract_text("hello world") == "hello world"

    def test_from_text_blocks(self):
        content = [
            {"type": "text", "text": "line 1"},
            {"type": "text", "text": "line 2"},
        ]
        assert extract_text(content) == "line 1\nline 2"

    def test_ignores_non_text_blocks(self):
        content = [
            {"type": "image", "source": {"type": "url", "url": "x"}},
            {"type": "text", "text": "hello"},
            {"type": "tool_use", "id": "t1", "name": "exec", "input": {}},
        ]
        assert extract_text(content) == "hello"

    def test_empty_blocks(self):
        assert extract_text([]) == ""

    def test_empty_string(self):
        assert extract_text("") == ""
