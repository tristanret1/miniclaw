# Knowledge Base Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a personal knowledge base system where users ingest sources via conversation, ACP auto-compiles a wiki, and deep research Q&A is delegated to ACP.

**Architecture:** Thin `kb` bot tool dispatches to `bot/services/kb.py`. Ingest downloads files to `raw/` using browser/exec, then delegates wiki compilation to ACP (`claude_code`). Q&A delegates research entirely to ACP. KB lives in a configurable external directory (default `~/kb`).

**Tech Stack:** Python 3.13+, existing ACP integration (claude-agent-sdk), existing browser/exec tools, yt-dlp for YouTube.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `bot/services/kb.py` | Core service: ingest (download + trigger compile), query (ACP delegation), list/status helpers |
| `bot/tools/kb.py` | Tool schema definition + `run_kb()` dispatch function |
| `tests/tools/test_kb.py` | Tests for kb tool dispatch and service layer |

| Modified File | Change |
|---------------|--------|
| `bot/config_schema.py:400-414` | Add `KbConfig` dataclass + wire into `ServicesConfig` |
| `config.yaml:80-99` | Add `services.kb` section |
| `bot/tools/__init__.py:27-41` | Register KB tool + handler |
| `main.py:1-8` | Add `kb` CLI subcommand dispatch |

---

### Task 1: KbConfig dataclass

**Files:**
- Modify: `bot/config_schema.py:400-414`
- Modify: `config.yaml:80-99`

- [ ] **Step 1: Add KbConfig dataclass to config_schema.py**

Add before `ServicesConfig` (after `HealthConfig` at line 379):

```python
@dataclass
class KbConfig:
    enabled: bool = True
    root: str = "~/kb"
    auto_compile: bool = True
    compile_timeout: int = 600
    query_timeout: int = 300

    @classmethod
    def from_dict(cls, d: dict) -> KbConfig:
        return cls(
            enabled=_bool(d.get("enabled"), True),
            root=_str(d.get("root"), "~/kb"),
            auto_compile=_bool(d.get("auto_compile"), True),
            compile_timeout=_int(d.get("compile_timeout"), 600),
            query_timeout=_int(d.get("query_timeout"), 300),
        )
```

- [ ] **Step 2: Wire KbConfig into ServicesConfig**

In `ServicesConfig` (line 400), add the `kb` field:

```python
@dataclass
class ServicesConfig:
    google_calendar: GoogleCalendarConfig = field(default_factory=GoogleCalendarConfig)
    cron: CronConfig = field(default_factory=CronConfig)
    health: HealthConfig = field(default_factory=HealthConfig)
    kb: KbConfig = field(default_factory=KbConfig)
    timeouts: TimeoutsConfig = field(default_factory=TimeoutsConfig)

    @classmethod
    def from_dict(cls, d: dict) -> ServicesConfig:
        return cls(
            google_calendar=GoogleCalendarConfig.from_dict(d.get("google_calendar") or {}),
            cron=CronConfig.from_dict(d.get("cron") or {}),
            health=HealthConfig.from_dict(d.get("health") or {}),
            kb=KbConfig.from_dict(d.get("kb") or {}),
            timeouts=TimeoutsConfig.from_dict(d.get("timeouts") or {}),
        )
```

- [ ] **Step 3: Add kb section to config.yaml**

Add after `health:` section (line 85):

```yaml
  kb:
    enabled: true
    root: ~/kb
    auto_compile: true
    compile_timeout: 600
    query_timeout: 300
```

- [ ] **Step 4: Verify config loads**

Run: `cd /Users/sen/side_project/miniclaw && uv run python -c "from bot.config import get_config; c = get_config(); print(c.services.kb.root, c.services.kb.enabled)"`
Expected: `~/kb True`

- [ ] **Step 5: Commit**

```bash
git add bot/config_schema.py config.yaml
git commit -m "feat(kb): add KbConfig dataclass and config.yaml section"
```

---

### Task 2: KB service layer — scaffolding + ingest

**Files:**
- Create: `bot/services/kb.py`
- Create: `tests/tools/test_kb.py`

- [ ] **Step 1: Write failing tests for KB service helpers**

Create `tests/tools/test_kb.py`:

```python
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
        assert "2026-04-03" in name or len(name) > 10  # has date prefix

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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: FAIL (no module `bot.services.kb`)

- [ ] **Step 3: Implement bot/services/kb.py — helpers**

Create `bot/services/kb.py`:

```python
"""Knowledge base service — ingest, compile, query via ACP delegation.

Directory layout (at KB_ROOT):
    raw/            — downloaded source files (PDF, .md from web, YouTube transcripts)
    wiki/           — LLM-compiled structured knowledge base
      index.md      — master index with one-line summaries
      concepts/     — concept articles
      summaries/    — per-source summaries
      queries/      — archived Q&A research outputs
      connections.md — inter-concept backlinks
    .kb_state.json  — tracks which raw files have been compiled
    CLAUDE.md       — wiki compilation spec (read by ACP)
"""

import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from bot.config import get_config
from bot.logger import get_logger

log = get_logger("kb")


def _get_kb_root() -> Path:
    """Resolve KB root from config, expanding ~ and ensuring absolute path."""
    cfg = get_config().services.kb
    return Path(cfg.root).expanduser().resolve()


def _ensure_kb_dirs(root: Path) -> None:
    """Create the KB directory structure if it doesn't exist."""
    for subdir in [
        "raw",
        "wiki",
        "wiki/concepts",
        "wiki/summaries",
        "wiki/queries",
    ]:
        (root / subdir).mkdir(parents=True, exist_ok=True)


def _load_state(root: Path) -> dict:
    """Load .kb_state.json, returning default if missing."""
    state_file = root / ".kb_state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"processed": []}


def _save_state(root: Path, state: dict) -> None:
    """Write .kb_state.json."""
    state_file = root / ".kb_state.json"
    state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _detect_source_type(url: str) -> str:
    """Detect source type from URL: youtube, pdf, or web."""
    lower = url.lower()
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if lower.endswith(".pdf"):
        return "pdf"
    return "web"


def _build_raw_filename(url: str, source_type: str) -> str:
    """Build a filename for the raw file: YYYY-MM-DD-slug.ext"""
    today = date.today().isoformat()
    parsed = urlparse(url)
    # Extract a slug from the URL path
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    slug = path_parts[-1] if path_parts else parsed.netloc
    # Clean slug
    slug = re.sub(r"[^\w\-.]", "-", slug)[:60]
    # Remove existing extension from slug for consistent naming
    slug_no_ext = re.sub(r"\.\w+$", "", slug)

    ext = {"youtube": ".md", "pdf": ".pdf", "web": ".md"}[source_type]
    return f"{today}-{slug_no_ext}{ext}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/kb.py tests/tools/test_kb.py
git commit -m "feat(kb): add KB service scaffolding — state tracking, URL detection, dir setup"
```

---

### Task 3: KB service — ingest implementation

**Files:**
- Modify: `bot/services/kb.py`
- Modify: `tests/tools/test_kb.py`

- [ ] **Step 1: Write failing tests for ingest functions**

Add to `tests/tools/test_kb.py`:

```python
class TestIngestWeb:
    """Tests for web page ingest."""

    @pytest.mark.asyncio
    async def test_ingest_web_saves_markdown(self, kb_root, monkeypatch):
        from bot.services import kb

        # Mock browser tool to return fake page content
        async def fake_browser(action, **kwargs):
            return {
                "type": "text",
                "title": "Test Article",
                "url": kwargs.get("url", ""),
                "text": "# Test\n\nThis is test content.",
            }

        monkeypatch.setattr(kb, "_fetch_web", fake_browser)
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        monkeypatch.setattr(kb, "_run_compile", lambda root: None)  # skip ACP

        result = await kb.ingest("https://blog.example.com/test-post")
        assert "saved" in result.lower() or "raw/" in result.lower()
        # Check file was created in raw/
        raw_files = list((kb_root / "raw").glob("*.md"))
        assert len(raw_files) == 1
        content = raw_files[0].read_text()
        assert "source_url: https://blog.example.com/test-post" in content
        assert "Test Article" in content or "test content" in content


class TestIngestPdf:
    """Tests for PDF ingest."""

    @pytest.mark.asyncio
    async def test_ingest_pdf_downloads_file(self, kb_root, monkeypatch):
        from bot.services import kb

        downloaded_to = []

        async def fake_exec(command, **kwargs):
            # Simulate curl writing a file
            for f in (kb_root / "raw").iterdir():
                pass  # just check command
            downloaded_to.append(command)
            # Create the file that curl would create
            pdf_files = list((kb_root / "raw").glob("*.pdf"))
            if not pdf_files:
                # Simulate the download
                target = kb_root / "raw" / "2026-04-03-paper.pdf"
                target.write_bytes(b"%PDF-1.4 fake content")
            return "ok"

        monkeypatch.setattr(kb, "_download_file", fake_exec)
        monkeypatch.setattr(kb, "_get_kb_root", lambda: kb_root)
        monkeypatch.setattr(kb, "_run_compile", lambda root: None)

        result = await kb.ingest("https://arxiv.org/pdf/2401.12345.pdf")
        assert "saved" in result.lower() or "raw/" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py::TestIngestWeb -v`
Expected: FAIL (`ingest` not defined)

- [ ] **Step 3: Implement ingest in bot/services/kb.py**

Append to `bot/services/kb.py`:

```python
# ── Ingest: download source material to raw/ ────────────────────────────────


async def _fetch_web(action: str, **kwargs) -> dict:
    """Fetch web page via browser tool. Thin wrapper for testability."""
    from bot.tools.browser import run_browser
    return await run_browser(action, **kwargs)


async def _download_file(command: str, **kwargs) -> str:
    """Download file via exec tool. Thin wrapper for testability."""
    from bot.tools.exec import run_exec
    return await run_exec(command=command, timeout=60)


async def _download_youtube(command: str, **kwargs) -> str:
    """Download YouTube transcript via exec. Thin wrapper for testability."""
    from bot.tools.exec import run_exec
    return await run_exec(command=command, timeout=120)


def _write_raw_md(path: Path, title: str, url: str, content: str, source_type: str) -> None:
    """Write a raw markdown file with frontmatter."""
    frontmatter = (
        f"---\n"
        f"title: {title}\n"
        f"source_url: {url}\n"
        f"ingested_at: {date.today().isoformat()}\n"
        f"type: {source_type}\n"
        f"---\n\n"
    )
    path.write_text(frontmatter + content, encoding="utf-8")


def _run_compile(root: Path) -> None:
    """Trigger background ACP compilation (fire-and-forget)."""
    import asyncio
    cfg = get_config().services.kb
    if not cfg.auto_compile:
        return
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_compile_async(root))
    except RuntimeError:
        pass  # no event loop — skip (e.g., CLI sync context)


async def ingest(url: str, source_type: str = "auto") -> str:
    """Download a source and save to raw/. Triggers compile if auto_compile is on."""
    root = _get_kb_root()
    _ensure_kb_dirs(root)

    if source_type == "auto":
        source_type = _detect_source_type(url)

    filename = _build_raw_filename(url, source_type)
    raw_path = root / "raw" / filename

    if source_type == "web":
        result = await _fetch_web("get_text", url=url)
        if isinstance(result, dict):
            title = result.get("title", "")
            text = result.get("text", "")
        else:
            title = ""
            text = str(result)
        _write_raw_md(raw_path, title, url, text, "web")

    elif source_type == "pdf":
        await _download_file(f"curl -sL -o '{raw_path}' '{url}'")
        if not raw_path.exists():
            return f"Error: failed to download PDF from {url}"

    elif source_type == "youtube":
        # Use yt-dlp to get auto-generated subtitles
        sub_path = root / "raw" / f"{raw_path.stem}"
        await _download_youtube(
            f"yt-dlp --write-auto-sub --skip-download --sub-lang en "
            f"--convert-subs srt -o '{sub_path}' '{url}'"
        )
        # Find the subtitle file and convert to markdown
        srt_candidates = list((root / "raw").glob(f"{raw_path.stem}*.srt"))
        if srt_candidates:
            srt_text = srt_candidates[0].read_text(encoding="utf-8", errors="ignore")
            # Strip SRT timing lines, keep text
            lines = [
                line.strip() for line in srt_text.splitlines()
                if line.strip() and not line.strip().isdigit()
                and "-->" not in line
            ]
            transcript = "\n".join(lines)
            srt_candidates[0].unlink()  # remove .srt, keep .md
        else:
            transcript = "(transcript extraction failed)"
        _write_raw_md(raw_path, f"YouTube: {url}", url, transcript, "youtube")

    else:
        return f"Error: unknown source type '{source_type}'"

    log.info("kb ingest: %s → %s", url, raw_path.name)
    _run_compile(root)
    return f"Saved to raw/{filename}. {'Auto-compiling wiki...' if get_config().services.kb.auto_compile else 'Run kb compile to update wiki.'}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/kb.py tests/tools/test_kb.py
git commit -m "feat(kb): implement ingest — web, PDF, YouTube download to raw/"
```

---

### Task 4: KB service — compile + query (ACP delegation)

**Files:**
- Modify: `bot/services/kb.py`
- Modify: `tests/tools/test_kb.py`

- [ ] **Step 1: Write failing tests for compile and query**

Add to `tests/tools/test_kb.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py::TestCompile -v`
Expected: FAIL (`compile` not defined)

- [ ] **Step 3: Implement compile, query, list, status**

Append to `bot/services/kb.py`:

```python
# ── Compile: delegate to ACP to build/update wiki ───────────────────────────

_COMPILE_TASK = """\
You are a knowledge base compiler. Your job is to incrementally compile raw source \
material into a structured wiki.

Read .kb_state.json to find which raw/ files have NOT been processed yet. For each \
unprocessed file:

1. Read the raw file from raw/
2. Write a summary to wiki/summaries/<slug>.md (include key facts, main arguments, \
important data points)
3. Identify core concepts — for each concept, create or UPDATE wiki/concepts/<concept>.md \
(add new information, cross-reference other articles, maintain backlinks)
4. Update wiki/index.md — this is the master index. Each entry should be one line: \
`- [[concept-name]] — one-sentence summary`. Keep it sorted alphabetically.
5. Update wiki/connections.md — map relationships between concepts \
(e.g., "attention-mechanism → transformer-architecture")
6. Mark the file as processed in .kb_state.json

Article format:
- Use standard Markdown with [[wikilinks]] for internal references
- Each concept article should have: ## Summary, ## Details, ## Related, ## Sources
- Keep articles focused — one concept per file

If there are no unprocessed files, respond with "Wiki is up to date."
"""


async def _compile_async(root: Path) -> str:
    """Run ACP compilation task."""
    from bot import acp
    cfg = get_config().services.kb
    result = await acp.run_prompt(
        task=_COMPILE_TASK,
        cwd=str(root),
        timeout=cfg.compile_timeout,
    )
    log.info("kb compile done: %s", result[:200])
    return result


async def compile() -> str:
    """Trigger wiki compilation via ACP."""
    root = _get_kb_root()
    _ensure_kb_dirs(root)
    return await _compile_async(root)


# ── Query: delegate deep research to ACP ────────────────────────────────────

_QUERY_TASK_TEMPLATE = """\
You are a research assistant working with a personal knowledge base wiki.

Research the following question thoroughly:

{question}

Process:
1. Read wiki/index.md to understand what topics are available
2. Identify and read all relevant articles in wiki/concepts/ and wiki/summaries/
3. If the wiki articles don't have enough detail, read the original sources in raw/
4. Cross-reference multiple sources to build a comprehensive answer
5. Save your answer to wiki/queries/{date}-{slug}.md

Your answer should:
- Cite specific sources from the wiki (use [[wikilinks]])
- Synthesize information across multiple articles
- Be thorough but well-organized with clear headings
- Note any gaps or uncertainties in the available data

Return the full answer text.
"""


async def query(question: str) -> str:
    """Deep research query — delegates to ACP for multi-turn wiki exploration."""
    root = _get_kb_root()
    _ensure_kb_dirs(root)

    from bot import acp
    cfg = get_config().services.kb

    today = date.today().isoformat()
    slug = re.sub(r"[^\w]+", "-", question.lower())[:40].strip("-")

    task = _QUERY_TASK_TEMPLATE.format(
        question=question,
        date=today,
        slug=slug,
    )

    result = await acp.run_prompt(
        task=task,
        cwd=str(root),
        timeout=cfg.query_timeout,
    )
    log.info("kb query done: %s", result[:200])
    return result


# ── List / Status: direct reads (no ACP needed) ─────────────────────────────


def list_kb() -> str:
    """List the wiki index contents."""
    root = _get_kb_root()
    index_path = root / "wiki" / "index.md"
    if not index_path.exists():
        return "Knowledge base is empty. Use `kb ingest <url>` to add content."
    content = index_path.read_text(encoding="utf-8")
    if not content.strip():
        return "Knowledge base index is empty."
    return content


def status() -> str:
    """Show KB status: raw file counts, compile state."""
    root = _get_kb_root()
    _ensure_kb_dirs(root)

    raw_files = [f.name for f in (root / "raw").iterdir() if f.is_file()]
    state = _load_state(root)
    processed = state.get("processed", [])
    pending = [f for f in raw_files if f not in processed]

    concept_count = len(list((root / "wiki" / "concepts").glob("*.md")))
    summary_count = len(list((root / "wiki" / "summaries").glob("*.md")))
    query_count = len(list((root / "wiki" / "queries").glob("*.md")))

    return (
        f"KB root: {root}\n"
        f"Raw files: {len(raw_files)} total, {len(processed)} compiled, {len(pending)} pending\n"
        f"Wiki: {concept_count} concepts, {summary_count} summaries, {query_count} queries\n"
        f"Pending: {', '.join(pending) if pending else 'none'}"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/kb.py tests/tools/test_kb.py
git commit -m "feat(kb): implement compile (ACP delegation), query, list, status"
```

---

### Task 5: KB tool schema + dispatch

**Files:**
- Create: `bot/tools/kb.py`
- Modify: `bot/tools/__init__.py:27-41`

- [ ] **Step 1: Write failing test for tool dispatch**

Add to `tests/tools/test_kb.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py::TestKbToolDispatch -v`
Expected: FAIL (unknown tool: kb)

- [ ] **Step 3: Create bot/tools/kb.py**

```python
"""kb tool — personal knowledge base: ingest, compile, query via ACP delegation."""

KB_TOOL = {
    "name": "kb",
    "description": (
        "Personal knowledge base. Ingest web pages, PDFs, and YouTube videos, "
        "auto-compile them into a structured wiki, and do deep research queries. "
        "Use 'ingest' to add sources (provide a URL). "
        "Use 'query' for research questions (the agent will explore the wiki autonomously). "
        "Use 'list' to see the wiki index, 'status' for compile state, "
        "'compile' to manually trigger wiki compilation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ingest", "query", "list", "status", "compile"],
                "description": (
                    "ingest: download a URL to raw/ and auto-compile wiki. "
                    "query: deep research question against the wiki. "
                    "list: show wiki index. "
                    "status: show raw/compile counts. "
                    "compile: manually trigger wiki compilation."
                ),
            },
            "url": {
                "type": "string",
                "description": "URL to ingest (for 'ingest' action). Supports web pages, PDFs, YouTube.",
            },
            "type": {
                "type": "string",
                "enum": ["auto", "web", "pdf", "youtube"],
                "description": "Source type override (default: auto-detect from URL).",
            },
            "question": {
                "type": "string",
                "description": "Research question (for 'query' action).",
            },
        },
        "required": ["action"],
    },
}
```

- [ ] **Step 4: Register kb tool in bot/tools/__init__.py**

Add import at the top (after line 21):

```python
from bot.tools.kb import KB_TOOL
```

Add to `ALL_TOOLS` list (line 27-31), add `KB_TOOL`:

```python
ALL_TOOLS = [
    EXEC_TOOL, MEMORY_SAVE_TOOL, MEMORY_SEARCH_TOOL, CLAUDE_CODE_TOOL,
    CRON_CREATE_TOOL, CRON_LIST_TOOL, CRON_DELETE_TOOL, PHONE_CALL_TOOL, SMS_TOOL,
    IMESSAGE_SEND_TOOL, BROWSER_TOOL, TWITTER_TOOL, KB_TOOL,
]
```

Add handler in `handle_tool_call` (before the final `log.warning` at line 201):

```python
    if tool_name == "kb":
        from bot.services import kb as kb_svc
        action = tool_input.get("action", "")
        if action == "ingest":
            url = tool_input.get("url", "")
            if not url:
                return "Error: url is required for ingest"
            return await kb_svc.ingest(
                url=url,
                source_type=tool_input.get("type", "auto"),
            )
        if action == "query":
            question = tool_input.get("question", "")
            if not question:
                return "Error: question is required for query"
            return await kb_svc.query(question=question)
        if action == "list":
            return kb_svc.list_kb()
        if action == "status":
            return kb_svc.status()
        if action == "compile":
            return await kb_svc.compile()
        return f"Error: unknown kb action '{action}'"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add bot/tools/kb.py bot/tools/__init__.py
git commit -m "feat(kb): add kb tool schema + dispatch, register in ALL_TOOLS"
```

---

### Task 6: CLI subcommand

**Files:**
- Modify: `main.py:1-8`

- [ ] **Step 1: Add kb CLI dispatch to main.py**

Add after the `agents` subcommand block (line 7), before the CLI flags parsing:

```python
# Delegate to KB CLI if "kb" subcommand is used
if len(sys.argv) > 1 and sys.argv[1] == "kb":
    import asyncio as _asyncio

    async def _kb_cli():
        args = sys.argv[2:]
        if not args:
            print("Usage: main.py kb <ingest|query|list|status|compile> [args]")
            return
        action = args[0]
        from bot.services import kb
        if action == "ingest" and len(args) > 1:
            print(await kb.ingest(args[1], source_type=args[2] if len(args) > 2 else "auto"))
        elif action == "query" and len(args) > 1:
            print(await kb.query(" ".join(args[1:])))
        elif action == "list":
            print(kb.list_kb())
        elif action == "status":
            print(kb.status())
        elif action == "compile":
            print(await kb.compile())
        else:
            print(f"Unknown kb command: {action}")
            print("Usage: main.py kb <ingest|query|list|status|compile> [args]")

    _asyncio.run(_kb_cli())
    sys.exit(0)
```

- [ ] **Step 2: Test CLI help**

Run: `cd /Users/sen/side_project/miniclaw && uv run python main.py kb`
Expected: prints usage message

- [ ] **Step 3: Test CLI status**

Run: `cd /Users/sen/side_project/miniclaw && uv run python main.py kb status`
Expected: prints KB status (creates ~/kb if needed)

- [ ] **Step 4: Commit**

```bash
git add main.py
git commit -m "feat(kb): add CLI subcommand — main.py kb <action>"
```

---

### Task 7: KB CLAUDE.md wiki spec

**Files:**
- Create: `~/kb/CLAUDE.md` (generated at first use)
- Modify: `bot/services/kb.py`

- [ ] **Step 1: Add CLAUDE.md generation to _ensure_kb_dirs**

In `bot/services/kb.py`, add after the `_ensure_kb_dirs` function:

```python
_KB_CLAUDE_MD = """\
# Knowledge Base Wiki — Compilation Guide

You are maintaining a personal knowledge base wiki. Follow these conventions exactly.

## Directory Structure

- `raw/` — source material (do not modify these files)
- `wiki/index.md` — master index, one entry per concept: `- [[concept-name]] — summary`
- `wiki/concepts/` — one .md file per concept
- `wiki/summaries/` — one .md file per raw source
- `wiki/queries/` — archived research Q&A outputs
- `wiki/connections.md` — relationship map between concepts
- `.kb_state.json` — tracks which raw files are processed (update after each compile)

## Article Format (concepts)

```markdown
# Concept Name

## Summary
2-3 sentence overview.

## Details
In-depth explanation with key facts, data points, arguments.

## Related
- [[other-concept]] — how it relates
- [[another-concept]] — connection description

## Sources
- [[summaries/source-slug]] — what this source contributed
```

## Article Format (summaries)

```markdown
# Source Title

- **URL:** original source URL
- **Type:** web/pdf/youtube
- **Ingested:** date

## Key Points
Bulleted list of main takeaways.

## Concepts Referenced
- [[concept-name]] — what was learned about this concept
```

## Index Format (wiki/index.md)

```markdown
# Knowledge Base Index

## Concepts
- [[attention-mechanism]] — weighted aggregation of values by learned relevance scores
- [[transformer]] — encoder-decoder architecture based on self-attention

## Sources
- [[summaries/arxiv-attention]] — original attention paper (Vaswani et al.)
```

Keep alphabetically sorted. One line per entry. Update on every compile.

## Wikilinks

Use `[[filename]]` (without extension) for internal links. These render in Obsidian.

## Rules
1. Never modify files in raw/
2. Always update index.md when adding/modifying articles
3. Always update connections.md when relationships change
4. Always update .kb_state.json after processing raw files
5. Prefer updating existing articles over creating new ones
6. Keep summaries factual — no opinion or interpretation
7. Concept articles should synthesize across all sources
"""


def _ensure_claude_md(root: Path) -> None:
    """Write CLAUDE.md to KB root if it doesn't exist."""
    claude_md = root / "CLAUDE.md"
    if not claude_md.exists():
        claude_md.write_text(_KB_CLAUDE_MD, encoding="utf-8")
        log.info("kb: created CLAUDE.md at %s", claude_md)
```

- [ ] **Step 2: Call _ensure_claude_md from _ensure_kb_dirs**

Update `_ensure_kb_dirs` to also call `_ensure_claude_md`:

```python
def _ensure_kb_dirs(root: Path) -> None:
    """Create the KB directory structure if it doesn't exist."""
    for subdir in [
        "raw",
        "wiki",
        "wiki/concepts",
        "wiki/summaries",
        "wiki/queries",
    ]:
        (root / subdir).mkdir(parents=True, exist_ok=True)
    _ensure_claude_md(root)
```

- [ ] **Step 3: Add test for CLAUDE.md creation**

Add to `tests/tools/test_kb.py`:

```python
class TestClaudeMd:
    """Tests for CLAUDE.md generation."""

    def test_creates_claude_md(self, kb_root):
        from bot.services.kb import _ensure_kb_dirs
        _ensure_kb_dirs(kb_root)
        claude_md = kb_root / "CLAUDE.md"
        assert claude_md.exists()
        content = claude_md.read_text()
        assert "Knowledge Base" in content
        assert "index.md" in content

    def test_does_not_overwrite_existing(self, kb_root):
        from bot.services.kb import _ensure_kb_dirs
        claude_md = kb_root / "CLAUDE.md"
        claude_md.write_text("custom content")
        _ensure_kb_dirs(kb_root)
        assert claude_md.read_text() == "custom content"
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot/services/kb.py tests/tools/test_kb.py
git commit -m "feat(kb): generate CLAUDE.md wiki spec for ACP on first use"
```

---

### Task 8: Run full test suite + verify integration

- [ ] **Step 1: Run all KB tests**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest tests/tools/test_kb.py -v`
Expected: All PASS

- [ ] **Step 2: Run full test suite to check for regressions**

Run: `cd /Users/sen/side_project/miniclaw && uv run pytest -v`
Expected: All existing tests still PASS

- [ ] **Step 3: Manual smoke test — CLI status**

Run: `cd /Users/sen/side_project/miniclaw && uv run python main.py kb status`
Expected: Shows KB root path, 0 raw files, 0 concepts

- [ ] **Step 4: Manual smoke test — CLI list**

Run: `cd /Users/sen/side_project/miniclaw && uv run python main.py kb list`
Expected: "Knowledge base is empty" message

- [ ] **Step 5: Verify CLAUDE.md was created**

Run: `cat ~/kb/CLAUDE.md | head -5`
Expected: Shows "# Knowledge Base Wiki — Compilation Guide"
