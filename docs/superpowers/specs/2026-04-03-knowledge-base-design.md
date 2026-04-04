# Knowledge Base Feature — Design Spec

**Date**: 2026-04-03
**Approach**: ACP-delegated (Option B)
**Status**: Approved

---

## Overview

Personal knowledge base system for MiniClaw. Users ingest source material (web pages, PDFs, YouTube videos) through conversation with the bot. An ACP agent (Claude Code) automatically compiles raw sources into a structured markdown wiki. Users query the wiki through deep research — the ACP agent reads the index, follows references across articles, and produces comprehensive answers.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Interface | CLI + bot tool + Obsidian viewing | Full flexibility |
| Ingest trigger | Conversation-driven | Agent auto-downloads via browser/exec |
| Compilation | Auto incremental after each ingest | No manual step needed |
| Storage location | Independent configurable directory (default `~/kb`) | KB data can grow large, separate from bot repo |
| Q&A mode | Deep research via ACP | Multi-turn autonomous reading, not simple retrieval |
| Output format | Markdown only (MVP) | Marp/matplotlib deferred |

## Architecture

```
User conversation (Discord / Feishu / CLI)
    |
    v
bot recognizes KB intent
    |
    +-- kb(action="ingest", ...) --> download to raw/, then delegate ACP for incremental compile
    +-- kb(action="query", ...)  --> delegate ACP for multi-turn research in wiki/
    +-- kb(action="list/status") --> read wiki index directly, no ACP needed
    
ACP agent (claude_code)
    |  cwd = KB_ROOT
    |  reads CLAUDE.md (wiki spec + compile instructions)
    |
    +-- Compile: read new raw/ files -> update wiki/ articles + index.md
    +-- Research: read wiki/index.md -> find relevant articles -> multi-turn reading -> write answer
```

## Directory Structure

Configurable root path, default `~/kb`:

```
~/kb/
+-- CLAUDE.md              # Wiki spec: directory structure, article format, indexing rules
+-- raw/                   # Raw data (agent-downloaded PDFs, web .md, YouTube transcripts)
|   +-- 2026-04-03-arxiv-attention.pdf
|   +-- 2026-04-03-blog-transformers.md
|   +-- 2026-04-03-youtube-karpathy.md
+-- wiki/                  # LLM-compiled structured knowledge base
|   +-- index.md           # Master index: all concepts/articles with one-line summaries + links
|   +-- concepts/          # Concept articles
|   |   +-- attention-mechanism.md
|   |   +-- transformer-architecture.md
|   +-- summaries/         # Source file summaries
|   |   +-- arxiv-attention.md
|   |   +-- blog-transformers.md
|   +-- queries/           # Archived Q&A research outputs
|   |   +-- 2026-04-03-attention-vs-memory.md
|   +-- connections.md     # Inter-concept relationship map (backlinks)
+-- .kb_state.json         # Compile state tracking (which raw files have been processed)
```

## Ingest Flow

### Step 1: Download to raw/ (thin logic in `bot/services/kb.py`)

Bot tool layer handles download using existing tools:

- **Web pages** -> call existing `browser` tool `get_text` action -> save as `.md`
- **PDFs** -> `exec` calls `curl` to download to raw/, filename with date prefix
- **YouTube** -> `exec` calls `yt-dlp --write-auto-sub --skip-download` for transcript -> save as `.md`
- Each raw file gets frontmatter: `source_url`, `ingested_at`, `type`

### Step 2: Delegate ACP for incremental compile (background, non-blocking)

```python
claude_code(
    task="Compile new content into the wiki. Read .kb_state.json to find unprocessed raw files. "
         "For each: write a summary, extract concepts, update/create concept articles, "
         "update index.md and connections.md. Mark processed in .kb_state.json.",
    cwd=KB_ROOT,
    timeout=600,
)
```

ACP reads `CLAUDE.md` for wiki conventions, then autonomously:
1. Read `.kb_state.json` to find unprocessed raw files
2. For each new file: write summary in `wiki/summaries/`
3. Extract concepts -> create or update articles in `wiki/concepts/`
4. Update `wiki/index.md` (master index with one-line summaries)
5. Update `wiki/connections.md` (backlinks, relationships)
6. Mark files as processed in `.kb_state.json`

### Design rationale

- Download logic stays in `kb.py` (needs browser/exec tools, simple deterministic logic)
- Compile logic fully delegated to ACP (needs LLM understanding, creative organization)
- Compile is async — ingest returns "saved, compiling..." immediately

## Q&A Deep Research

Fully delegated to ACP:

```python
claude_code(
    task=f"""
    Research the following question in the knowledge base: {question}
    
    1. Read wiki/index.md to understand the full scope of the KB
    2. Based on the question, identify and read relevant articles
    3. If wiki articles are insufficient, read raw/ source materials
    4. Synthesize all information into a detailed answer
    5. Save the answer to wiki/queries/YYYY-MM-DD-{slug}.md
    """,
    cwd=KB_ROOT,
    timeout=300,
)
```

ACP autonomously:
1. Reads `wiki/index.md` — LLM-maintained global index with one-line summaries per concept
2. Identifies which articles to read based on the question
3. Reads articles, cross-references
4. Writes comprehensive answer (markdown)
5. Archives answer to `wiki/queries/` (queries "file back" into the KB)

No RAG needed at this scale — `index.md` serves as the LLM-maintained retrieval index.

## Tool Schema

```python
# bot/tools/kb.py
KB_TOOL = {
    "name": "kb",
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["ingest", "query", "list", "status", "compile"],
            },
            "url": { "type": "string" },         # for ingest
            "type": { "type": "string" },         # auto/web/pdf/youtube — for ingest
            "question": { "type": "string" },     # for query
        },
        "required": ["action"],
    },
}
```

## CLI Interface

```bash
uv run python main.py kb ingest <url>       # download + compile
uv run python main.py kb query "question"   # deep research
uv run python main.py kb list               # show wiki index
uv run python main.py kb compile            # manual compile trigger
uv run python main.py kb status             # compilation state
```

CLI calls the same `bot/services/kb.py` functions directly.

## Configuration

New section in `config.yaml`:

```yaml
services:
  kb:
    enabled: true
    root: ~/kb
    auto_compile: true
    compile_timeout: 600
    query_timeout: 300
```

## Files to Create

| File | Purpose |
|------|---------|
| `bot/tools/kb.py` | Tool schema + dispatch |
| `bot/services/kb.py` | Core service: ingest (download), compile/query (ACP delegation) |
| `~/kb/CLAUDE.md` | Wiki compilation spec (ACP instruction file) |

## Files to Modify

| File | Change |
|------|--------|
| `bot/tools/__init__.py` | Register kb tool + handler |
| `bot/config_schema.py` | Add KbConfig dataclass |
| `config.yaml` | Add `services.kb` section |
| `main.py` | Add `kb` CLI subcommand |

## Out of Scope (future)

- Marp slide generation
- matplotlib/visualization output
- Health check / linting passes over wiki
- Custom search engine over wiki
- Synthetic data generation / finetuning
