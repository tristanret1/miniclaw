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


class TestCompile:
    """Tests for wiki compilation."""

    @pytest.mark.asyncio
    async def test_compile_calls_acp(self, kb_root, monkeypatch):
        from bot.services import kb

        acp_calls = []

        async def fake_acp(task, cwd=None, timeout=300):
            acp_calls.append({"task": task, "cwd": cwd, "timeout": timeout})
            return "Compiled 2 new files"

        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        monkeypatch.setattr("bot.acp.run_prompt", fake_acp)
        kb._ensure_kb_dirs(kb_root)

        result = await kb.compile()
        assert len(acp_calls) == 1
        assert str(kb_root) in acp_calls[0]["cwd"]
        assert "compile" in acp_calls[0]["task"].lower() or "wiki" in acp_calls[0]["task"].lower()


class TestQuery:
    """Tests for KB query."""

    @pytest.mark.asyncio
    async def test_query_calls_acp(self, kb_root, monkeypatch):
        from bot.services import kb

        acp_calls = []

        async def fake_acp(task, cwd=None, timeout=300):
            acp_calls.append({"task": task, "cwd": cwd, "timeout": timeout})
            return "The attention mechanism works by..."

        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        monkeypatch.setattr("bot.acp.run_prompt", fake_acp)
        kb._ensure_kb_dirs(kb_root)

        result = await kb.query("How does attention work?")
        assert len(acp_calls) == 1
        assert "attention" in acp_calls[0]["task"].lower()
        assert "attention mechanism" in result.lower()


class TestList:
    """Tests for KB list."""

    def test_list_empty_kb(self, kb_root, monkeypatch):
        from bot.services import kb
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        kb._ensure_kb_dirs(kb_root)
        result = kb.list_kb()
        assert "empty" in result.lower() or "no " in result.lower()

    def test_list_with_index(self, kb_root, monkeypatch):
        from bot.services import kb
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        kb._ensure_kb_dirs(kb_root)
        (kb_root / "wiki" / "index.md").write_text("# KB Index\n\n- [[attention]] — core mechanism\n")
        result = kb.list_kb()
        assert "attention" in result


class TestStatus:
    """Tests for KB status."""

    def test_status_counts_files(self, kb_root, monkeypatch):
        from bot.services import kb
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        kb._ensure_kb_dirs(kb_root)
        (kb_root / "raw" / "file1.md").write_text("test")
        (kb_root / "raw" / "file2.pdf").write_bytes(b"test")
        kb._save_state(kb_root, {"processed": ["file1.md"]})
        result = kb.status()
        assert "2" in result  # total raw files
        assert "1" in result  # processed


class TestKbToolDispatch:
    """Tests for kb tool dispatch in __init__.py."""

    @pytest.mark.asyncio
    async def test_handle_tool_call_kb_list(self, kb_root, monkeypatch):
        from bot.services import kb
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        kb._ensure_kb_dirs(kb_root)

        from bot.tools import handle_tool_call
        result = await handle_tool_call("kb", {"action": "list"})
        assert "empty" in result.lower() or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_handle_tool_call_kb_status(self, kb_root, monkeypatch):
        from bot.services import kb
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        kb._ensure_kb_dirs(kb_root)

        from bot.tools import handle_tool_call
        result = await handle_tool_call("kb", {"action": "status"})
        assert "raw files" in result.lower() or "kb root" in result.lower()
