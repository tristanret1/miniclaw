#!/usr/bin/env python3
"""Debug tool: dump session history by session key.

Usage:
    python debug_history.py <session_key>          # dump messages as JSON
    python debug_history.py <session_key> --pretty  # human-readable format
    python debug_history.py --list                  # list all session keys
    python debug_history.py <session_key> --last N  # only last N messages
"""

import argparse
import asyncio
import json
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Minimal DB access — avoids importing bot.config (which needs .env / Discord
# token) so the script works standalone.
# ---------------------------------------------------------------------------

WORKSPACE_DIR = Path(__file__).resolve().parent / "workspace"
DEFAULT_DB = WORKSPACE_DIR / "sessions.db"


def _sqlite_load(db_path: Path, session_key: str, limit: int | None = None) -> list[dict]:
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    if limit:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM ("
            "  SELECT id, role, content, created_at FROM messages"
            "  WHERE session_key = ? ORDER BY id DESC LIMIT ?"
            ") ORDER BY id ASC",
            (session_key, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE session_key = ? ORDER BY id ASC",
            (session_key,),
        ).fetchall()
    conn.close()

    messages = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        messages.append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": row["created_at"],
        })
    return messages


async def _pg_load(session_key: str, limit: int | None = None) -> list[dict]:
    """Load from PostgreSQL (requires DATABASE_URL in env)."""
    import os
    import ssl

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("error: DATABASE_URL not set (needed for --pg mode)", file=sys.stderr)
        sys.exit(1)

    import asyncpg
    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(url, ssl=ssl_ctx)

    if limit:
        rows = await conn.fetch(
            "SELECT id, role, content, created_at FROM ("
            "  SELECT id, role, content, created_at FROM messages"
            "  WHERE session_key = $1 ORDER BY id DESC LIMIT $2"
            ") sub ORDER BY id ASC",
            session_key, limit,
        )
    else:
        rows = await conn.fetch(
            "SELECT id, role, content, created_at FROM messages "
            "WHERE session_key = $1 ORDER BY id ASC",
            session_key,
        )
    await conn.close()

    messages = []
    for row in rows:
        try:
            content = json.loads(row["content"])
        except (json.JSONDecodeError, TypeError):
            content = row["content"]
        messages.append({
            "id": row["id"],
            "role": row["role"],
            "content": content,
            "created_at": str(row["created_at"]),
        })
    return messages


def _list_sessions(db_path: Path) -> None:
    if not db_path.exists():
        print(f"error: database not found: {db_path}", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT session_key, COUNT(*) as msg_count, "
        "MIN(created_at) as first_msg, MAX(created_at) as last_msg "
        "FROM messages GROUP BY session_key ORDER BY last_msg DESC"
    ).fetchall()
    conn.close()

    if not rows:
        print("No sessions found.")
        return

    print(f"{'SESSION KEY':<40} {'MSGS':>5}  {'FIRST MESSAGE':<20} {'LAST MESSAGE':<20}")
    print("-" * 90)
    for row in rows:
        print(f"{row['session_key']:<40} {row['msg_count']:>5}  {row['first_msg']:<20} {row['last_msg']:<20}")


async def _list_sessions_pg() -> None:
    import os
    import ssl

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("error: DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    import asyncpg
    ssl_ctx = ssl.create_default_context()
    conn = await asyncpg.connect(url, ssl=ssl_ctx)
    rows = await conn.fetch(
        "SELECT session_key, COUNT(*) as msg_count, "
        "MIN(created_at) as first_msg, MAX(created_at) as last_msg "
        "FROM messages GROUP BY session_key ORDER BY last_msg DESC"
    )
    await conn.close()

    if not rows:
        print("No sessions found.")
        return

    print(f"{'SESSION KEY':<40} {'MSGS':>5}  {'FIRST MESSAGE':<20} {'LAST MESSAGE':<20}")
    print("-" * 90)
    for row in rows:
        print(f"{row['session_key']:<40} {row['msg_count']:>5}  {str(row['first_msg']):<20} {str(row['last_msg']):<20}")


# ---------------------------------------------------------------------------
# Pretty printer
# ---------------------------------------------------------------------------

def _pretty_print(messages: list[dict]) -> None:
    """Human-readable output."""
    for msg in messages:
        role = msg["role"].upper()
        ts = msg.get("created_at", "")
        print(f"\n{'='*60}")
        print(f"[{role}]  id={msg['id']}  {ts}")
        print("-" * 60)

        content = msg["content"]
        if isinstance(content, str):
            print(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    print(block)
                    continue
                btype = block.get("type", "unknown")
                if btype == "text":
                    print(block.get("text", ""))
                elif btype == "tool_use":
                    print(f"  [tool_use] {block.get('name', '?')} id={block.get('id', '?')}")
                    print(f"  input: {json.dumps(block.get('input', {}), ensure_ascii=False, indent=2)}")
                elif btype == "tool_result":
                    print(f"  [tool_result] tool_use_id={block.get('tool_use_id', '?')}")
                    result_content = block.get("content", "")
                    if isinstance(result_content, str):
                        # Truncate long tool results
                        if len(result_content) > 500:
                            print(f"  {result_content[:500]}... ({len(result_content)} chars)")
                        else:
                            print(f"  {result_content}")
                    else:
                        print(f"  {json.dumps(result_content, ensure_ascii=False, indent=2)}")
                elif btype == "image":
                    src = block.get("source", {})
                    print(f"  [image] {src.get('type', '?')}: {src.get('url', '?')}")
                else:
                    print(f"  [{btype}] {json.dumps(block, ensure_ascii=False)}")
        else:
            print(json.dumps(content, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Debug session history")
    parser.add_argument("session_key", nargs="?", help="Session key (channel_id:user_id)")
    parser.add_argument("--list", action="store_true", help="List all session keys")
    parser.add_argument("--pretty", action="store_true", help="Human-readable output")
    parser.add_argument("--last", type=int, metavar="N", help="Only show last N messages")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"SQLite DB path (default: {DEFAULT_DB})")
    parser.add_argument("--pg", action="store_true", help="Use PostgreSQL (requires DATABASE_URL env)")
    args = parser.parse_args()

    if args.list:
        if args.pg:
            asyncio.run(_list_sessions_pg())
        else:
            _list_sessions(args.db)
        return

    if not args.session_key:
        parser.error("session_key is required (or use --list)")

    if args.pg:
        messages = asyncio.run(_pg_load(args.session_key, args.last))
    else:
        messages = _sqlite_load(args.db, args.session_key, args.last)

    if not messages:
        print(f"No messages found for session: {args.session_key}", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(messages)} messages for session: {args.session_key}\n", file=sys.stderr)

    if args.pretty:
        _pretty_print(messages)
    else:
        # Output as JSON message list (compatible with Anthropic API format)
        api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]
        print(json.dumps(api_messages, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
