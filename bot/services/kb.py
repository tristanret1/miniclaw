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


# ── Placeholder for Task 4 ────────────────────────────────────────────────────


async def _compile_async(root: Path) -> str:
    """Run ACP compilation task. (Implemented in Task 4)"""
    return "compile not yet implemented"


# ── Ingest: download source material to raw/ ─────────────────────────────────


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
