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


class TestIngestWeb:
    """Tests for web page ingest."""

    @pytest.mark.asyncio
    async def test_ingest_web_saves_markdown(self, kb_root, monkeypatch):
        from bot.services import kb

        # Mock browser tool to return fake page content
        async def fake_fetch_web(action, **kwargs):
            return {
                "type": "text",
                "title": "Test Article",
                "url": kwargs.get("url", ""),
                "text": "# Test\n\nThis is test content.",
            }

        monkeypatch.setattr(kb, "_fetch_web", fake_fetch_web)
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        monkeypatch.setattr(kb, "_run_compile", lambda root: None)  # skip ACP
        kb._ensure_kb_dirs(kb_root)

        result = await kb.ingest("https://blog.example.com/test-post")
        assert "saved" in result.lower() or "raw/" in result.lower()
        # Check file was created in raw/
        raw_files = list((kb_root / "raw").glob("*.md"))
        assert len(raw_files) == 1
        content = raw_files[0].read_text()
        assert "source_url: https://blog.example.com/test-post" in content


class TestIngestPdf:
    """Tests for PDF ingest."""

    @pytest.mark.asyncio
    async def test_ingest_pdf_downloads_file(self, kb_root, monkeypatch):
        from bot.services import kb

        async def fake_download(command, **kwargs):
            # Simulate curl creating the file - extract path from command
            import re
            match = re.search(r"-o '([^']+)'", command)
            if match:
                Path(match.group(1)).write_bytes(b"%PDF-1.4 fake content")
            return "ok"

        monkeypatch.setattr(kb, "_download_file", fake_download)
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        monkeypatch.setattr(kb, "_run_compile", lambda root: None)
        kb._ensure_kb_dirs(kb_root)

        result = await kb.ingest("https://arxiv.org/pdf/2401.12345.pdf")
        assert "saved" in result.lower() or "raw/" in result.lower()
        raw_files = list((kb_root / "raw").glob("*.pdf"))
        assert len(raw_files) == 1
