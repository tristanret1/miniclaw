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
