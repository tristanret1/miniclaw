"""Tests for knowledge base service."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def kb_root(tmp_path):
    """Create a temporary KB root directory."""
    root = tmp_path / "kb"
    root.mkdir()
    return root


class TestKbState:
    """Tests for .kb_state.json tracking."""

    def test_load_empty_state(self, kb_root):
        from bot.services.kb import _load_state, _save_state
        state = _load_state(kb_root)
        assert state == {"processed": []}

    def test_save_and_load_state(self, kb_root):
        from bot.services.kb import _load_state, _save_state
        _save_state(kb_root, {"processed": ["file1.md", "file2.pdf"]})
        state = _load_state(kb_root)
        assert state["processed"] == ["file1.md", "file2.pdf"]


class TestDetectSourceType:
    """Tests for URL type detection."""

    def test_youtube_url(self):
        from bot.services.kb import _detect_source_type
        assert _detect_source_type("https://www.youtube.com/watch?v=abc123") == "youtube"
        assert _detect_source_type("https://youtu.be/abc123") == "youtube"

    def test_pdf_url(self):
        from bot.services.kb import _detect_source_type
        assert _detect_source_type("https://arxiv.org/pdf/2401.12345.pdf") == "pdf"
        assert _detect_source_type("https://example.com/paper.PDF") == "pdf"

    def test_web_url(self):
        from bot.services.kb import _detect_source_type
        assert _detect_source_type("https://blog.example.com/post") == "web"


class TestBuildRawFilename:
    """Tests for raw file naming."""

    def test_filename_from_url(self):
        from bot.services.kb import _build_raw_filename
        name = _build_raw_filename("https://arxiv.org/pdf/2401.12345.pdf", "pdf")
        assert name.endswith(".pdf")
        assert len(name) > 10  # has date prefix

    def test_filename_for_web(self):
        from bot.services.kb import _build_raw_filename
        name = _build_raw_filename("https://blog.example.com/great-post", "web")
        assert name.endswith(".md")

    def test_filename_for_youtube(self):
        from bot.services.kb import _build_raw_filename
        name = _build_raw_filename("https://youtube.com/watch?v=abc", "youtube")
        assert name.endswith(".md")


class TestEnsureKbDirs:
    """Tests for KB directory initialization."""

    def test_creates_dirs(self, kb_root):
        from bot.services.kb import _ensure_kb_dirs
        _ensure_kb_dirs(kb_root)
        assert (kb_root / "raw").is_dir()
        assert (kb_root / "wiki").is_dir()
        assert (kb_root / "wiki" / "concepts").is_dir()
        assert (kb_root / "wiki" / "summaries").is_dir()
        assert (kb_root / "wiki" / "queries").is_dir()
