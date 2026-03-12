"""Simple file-based memory system — Markdown files with keyword search."""

import re
from datetime import date
from pathlib import Path

from bot.config import WORKSPACE_DIR
from bot.logger import get_logger

log = get_logger("memory")

MEMORY_DIR = WORKSPACE_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def save(content: str, tags: list[str] | None = None) -> str:
    """Append a memory entry to today's daily log file."""
    today = date.today().isoformat()
    filepath = MEMORY_DIR / f"{today}.md"

    tag_line = ""
    if tags:
        tag_line = f"  tags: {', '.join(tags)}\n"

    entry = f"- {content}\n{tag_line}"

    is_new = not filepath.exists() or filepath.stat().st_size == 0
    with open(filepath, "a", encoding="utf-8") as f:
        if is_new:
            f.write(f"# {today}\n\n")
        f.write(entry + "\n")

    log.info("memory saved → %s (%d chars, tags=%s)", filepath.name, len(content), tags)
    return f"Saved to {filepath.name}"


def search(query: str, max_results: int = 10) -> str:
    """Search all memory files for lines matching query keywords."""
    md_files = sorted(MEMORY_DIR.glob("*.md"), reverse=True)
    if not md_files:
        return "No memories found."

    # Split query into keywords for matching
    keywords = [k.lower() for k in re.split(r"\s+", query.strip()) if k]
    if not keywords:
        return "Empty query."

    results: list[str] = []
    for filepath in md_files:
        text = filepath.read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), 1):
            line_lower = line.lower()
            if any(kw in line_lower for kw in keywords):
                results.append(f"[{filepath.name}:{i}] {line.strip()}")
                if len(results) >= max_results:
                    break
        if len(results) >= max_results:
            break

    if not results:
        return f"No matches for: {query}"

    log.info("memory search '%s' → %d result(s)", query, len(results))
    return "\n".join(results)
