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
