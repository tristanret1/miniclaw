"""Twitter tool — fetch tweets and user profiles via GetXAPI.

Supports: advanced search, user tweets, user media, user search.
Stores fetched tweets and users in PostgreSQL to avoid duplicate API calls.
"""

from __future__ import annotations

import json
from datetime import datetime

import httpx

from bot.config import get_secrets
from bot.logger import get_logger

log = get_logger("twitter")

GETXAPI_BASE = "https://api.getxapi.com/twitter"


def _get_token() -> str:
    return get_secrets().get("GETXAPI_TOKEN", "") or ""


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


def _parse_twitter_date(s: str) -> datetime | None:
    """Parse Twitter date format: 'Fri Apr 03 19:04:40 +0000 2026'."""
    try:
        return datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")
    except (ValueError, TypeError):
        return None


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_pool():
    from bot.storage.db import get_pool
    return await get_pool()


async def _upsert_user(conn, user: dict) -> None:
    """Insert or update a Twitter user profile."""
    if not user or not user.get("id"):
        return
    await conn.execute("""
        INSERT INTO twitter_users (
            id, user_name, name, is_verified, is_blue_verified,
            profile_picture, cover_picture, description, location,
            followers, following, tweets_count, listed,
            created_at, raw_json, fetched_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,now())
        ON CONFLICT (id) DO UPDATE SET
            user_name = EXCLUDED.user_name,
            name = EXCLUDED.name,
            is_verified = EXCLUDED.is_verified,
            is_blue_verified = EXCLUDED.is_blue_verified,
            profile_picture = EXCLUDED.profile_picture,
            cover_picture = EXCLUDED.cover_picture,
            description = EXCLUDED.description,
            location = EXCLUDED.location,
            followers = EXCLUDED.followers,
            following = EXCLUDED.following,
            tweets_count = EXCLUDED.tweets_count,
            listed = EXCLUDED.listed,
            raw_json = EXCLUDED.raw_json,
            fetched_at = now()
    """,
        user["id"],
        user.get("userName", ""),
        user.get("name", ""),
        user.get("isVerified", False),
        user.get("isBlueVerified", False),
        user.get("profilePicture", ""),
        user.get("coverPicture", ""),
        user.get("description", ""),
        user.get("location", ""),
        user.get("followers", 0),
        user.get("following", 0),
        user.get("tweets", 0),
        user.get("listed", 0),
        _parse_twitter_date(user.get("createdAt", "")),
        json.dumps(user, ensure_ascii=False),
    )


async def _upsert_tweet(conn, tweet: dict) -> bool:
    """Insert a tweet if not exists. Returns True if newly inserted."""
    if not tweet or not tweet.get("id"):
        return False
    existed = await conn.fetchval(
        "SELECT 1 FROM twitter_tweets WHERE id = $1", tweet["id"]
    )
    if existed:
        return False

    author = tweet.get("author") or {}
    media_json = json.dumps(tweet.get("media", []), ensure_ascii=False)
    quoted = tweet.get("quoted_tweet")
    quoted_json = json.dumps(quoted, ensure_ascii=False) if quoted else None

    await conn.execute("""
        INSERT INTO twitter_tweets (
            id, url, text, source, author_id, author_username,
            retweet_count, reply_count, like_count, quote_count, view_count,
            bookmark_count, lang, is_reply, in_reply_to_id, conversation_id,
            media_json, quoted_tweet_json, created_at, raw_json, fetched_at
        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,now())
        ON CONFLICT (id) DO NOTHING
    """,
        tweet["id"],
        tweet.get("url", ""),
        tweet.get("text", ""),
        tweet.get("source", ""),
        author.get("id", ""),
        author.get("userName", ""),
        tweet.get("retweetCount", 0),
        tweet.get("replyCount", 0),
        tweet.get("likeCount", 0),
        tweet.get("quoteCount", 0),
        tweet.get("viewCount", 0),
        tweet.get("bookmarkCount", 0),
        tweet.get("lang", ""),
        tweet.get("isReply", False),
        tweet.get("inReplyToId"),
        tweet.get("conversationId"),
        media_json,
        quoted_json,
        _parse_twitter_date(tweet.get("createdAt", "")),
        json.dumps(tweet, ensure_ascii=False),
    )

    # Also upsert the author
    if author.get("id"):
        await _upsert_user(conn, author)

    return True


async def _store_tweets(tweets: list[dict]) -> tuple[int, int]:
    """Store tweets in DB. Returns (new_count, skipped_count)."""
    pool = await _get_pool()
    if not pool:
        return len(tweets), 0  # No DB, treat all as new

    new, skipped = 0, 0
    async with pool.acquire() as conn:
        for t in tweets:
            if await _upsert_tweet(conn, t):
                new += 1
            else:
                skipped += 1
    return new, skipped


async def _store_users(users: list[dict]) -> tuple[int, int]:
    """Store users in DB. Returns (new_count, updated_count)."""
    pool = await _get_pool()
    if not pool:
        return len(users), 0

    async with pool.acquire() as conn:
        for u in users:
            await _upsert_user(conn, u)
    return len(users), 0


# ── API calls ─────────────────────────────────────────────────────────────────

async def _api_get(path: str, params: dict) -> dict:
    """Make a GET request to GetXAPI."""
    token = _get_token()
    if not token:
        return {"error": "GETXAPI_TOKEN not set in .env"}

    url = f"{GETXAPI_BASE}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers=_headers(), params=params)
        if resp.status_code != 200:
            return {"error": f"API returned {resp.status_code}: {resp.text[:500]}"}
        return resp.json()


def _format_tweet(t: dict) -> str:
    """Format a single tweet for display."""
    author = t.get("author") or {}
    name = author.get("name", "")
    username = author.get("userName", "")
    text = t.get("text", "")
    date = t.get("createdAt", "")
    url = t.get("url", "")
    stats = (
        f"❤️{t.get('likeCount', 0)} "
        f"🔁{t.get('retweetCount', 0)} "
        f"💬{t.get('replyCount', 0)} "
        f"👁{t.get('viewCount', 0)}"
    )
    media = t.get("media", [])
    media_str = ""
    if media:
        urls = [m.get("url", "") for m in media if m.get("url")]
        if urls:
            media_str = "\n  Media: " + ", ".join(urls)

    return f"@{username} ({name}) — {date}\n  {text}\n  {stats}  {url}{media_str}"


def _format_user(u: dict) -> str:
    """Format a single user for display."""
    return (
        f"@{u.get('userName', '')} ({u.get('name', '')})\n"
        f"  {u.get('description', '')}\n"
        f"  Followers: {u.get('followers', 0)} | Following: {u.get('following', 0)} | "
        f"Tweets: {u.get('tweets', 0)}\n"
        f"  {u.get('url', '')}"
    )


# ── Tool actions ──────────────────────────────────────────────────────────────

async def run_twitter(action: str, **kwargs) -> str:
    """Execute a Twitter tool action."""

    if action == "search_tweets":
        query = kwargs.get("query", "")
        if not query:
            return "Error: query is required"
        params = {"q": query}
        if kwargs.get("cursor"):
            params["cursor"] = kwargs["cursor"]

        data = await _api_get("/tweet/advanced_search", params)
        if "error" in data:
            return data["error"]

        tweets = data.get("tweets", [])
        new, skipped = await _store_tweets(tweets)

        lines = [f"Search: '{query}' — {data.get('tweet_count', 0)} results "
                 f"(new: {new}, already stored: {skipped})"]
        for t in tweets[:10]:
            lines.append(f"\n{_format_tweet(t)}")

        if data.get("has_more") and data.get("next_cursor"):
            lines.append(f"\n--- More results available. cursor: {data['next_cursor']}")
        return "\n".join(lines)

    elif action == "user_tweets":
        username = kwargs.get("username", "")
        if not username:
            return "Error: username is required"
        params = {"userName": username}
        if kwargs.get("cursor"):
            params["cursor"] = kwargs["cursor"]

        data = await _api_get("/user/tweets", params)
        if "error" in data:
            return data["error"]

        tweets = data.get("tweets", [])
        new, skipped = await _store_tweets(tweets)

        lines = [f"@{username} tweets — {data.get('tweet_count', 0)} results "
                 f"(new: {new}, already stored: {skipped})"]
        for t in tweets[:10]:
            lines.append(f"\n{_format_tweet(t)}")

        if data.get("has_more") and data.get("next_cursor"):
            lines.append(f"\n--- More results available. cursor: {data['next_cursor']}")
        return "\n".join(lines)

    elif action == "user_media":
        username = kwargs.get("username", "")
        if not username:
            return "Error: username is required"
        params = {"userName": username}
        if kwargs.get("cursor"):
            params["cursor"] = kwargs["cursor"]

        data = await _api_get("/user/media", params)
        if "error" in data:
            return data["error"]

        media_tweets = data.get("media", [])
        new, skipped = await _store_tweets(media_tweets)

        lines = [f"@{username} media — {data.get('tweet_count', 0)} results "
                 f"(new: {new}, already stored: {skipped})"]
        for t in media_tweets[:10]:
            lines.append(f"\n{_format_tweet(t)}")

        if data.get("has_more") and data.get("next_cursor"):
            lines.append(f"\n--- More results available. cursor: {data['next_cursor']}")
        return "\n".join(lines)

    elif action == "search_users":
        query = kwargs.get("query", "")
        if not query:
            return "Error: query is required"
        params = {"q": query}
        if kwargs.get("cursor"):
            params["cursor"] = kwargs["cursor"]

        data = await _api_get("/user/search", params)
        if "error" in data:
            return data["error"]

        users = data.get("users", [])
        await _store_users(users)

        lines = [f"User search: '{query}' — {data.get('user_count', 0)} results"]
        for u in users[:10]:
            lines.append(f"\n{_format_user(u)}")

        if data.get("has_more") and data.get("next_cursor"):
            lines.append(f"\n--- More results available. cursor: {data['next_cursor']}")
        return "\n".join(lines)

    elif action == "lookup_stored":
        # Search locally stored tweets/users without hitting the API
        query = kwargs.get("query", "")
        if not query:
            return "Error: query is required"

        pool = await _get_pool()
        if not pool:
            return "No database configured — stored lookup requires PostgreSQL."

        async with pool.acquire() as conn:
            # Search tweets
            tweets = await conn.fetch("""
                SELECT id, url, text, author_username, like_count, retweet_count,
                       view_count, created_at
                FROM twitter_tweets
                WHERE text ILIKE $1
                ORDER BY created_at DESC
                LIMIT 20
            """, f"%{query}%")

            # Search users
            users = await conn.fetch("""
                SELECT id, user_name, name, description, followers, following
                FROM twitter_users
                WHERE user_name ILIKE $1 OR name ILIKE $1 OR description ILIKE $1
                ORDER BY followers DESC
                LIMIT 10
            """, f"%{query}%")

        lines = [f"Stored lookup: '{query}'"]
        if tweets:
            lines.append(f"\n--- Tweets ({len(tweets)} matches) ---")
            for t in tweets:
                lines.append(
                    f"@{t['author_username']} ({t['created_at']}): "
                    f"{t['text'][:200]}\n  ❤️{t['like_count']} 🔁{t['retweet_count']} "
                    f"👁{t['view_count']}  {t['url']}"
                )
        if users:
            lines.append(f"\n--- Users ({len(users)} matches) ---")
            for u in users:
                lines.append(
                    f"@{u['user_name']} ({u['name']}) — "
                    f"{u['description'][:100]} — "
                    f"Followers: {u['followers']}"
                )
        if not tweets and not users:
            lines.append("No stored results found.")

        return "\n".join(lines)

    else:
        return (
            f"Error: unknown action '{action}'. "
            "Available: search_tweets, user_tweets, user_media, search_users, lookup_stored"
        )


# ── Tool schema ───────────────────────────────────────────────────────────────

TWITTER_TOOL = {
    "name": "twitter",
    "description": (
        "Fetch Twitter/X content via GetXAPI. Search tweets, get user timelines, "
        "get user media, search users. All fetched data is stored in the database "
        "to avoid duplicate API calls. Use 'lookup_stored' to search previously "
        "fetched content without hitting the API."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": [
                    "search_tweets", "user_tweets", "user_media",
                    "search_users", "lookup_stored",
                ],
                "description": (
                    "search_tweets: advanced search (q parameter). "
                    "user_tweets: get a user's timeline by username. "
                    "user_media: get a user's media tweets. "
                    "search_users: search for users. "
                    "lookup_stored: search locally stored tweets/users (no API call)."
                ),
            },
            "query": {
                "type": "string",
                "description": "Search query (for search_tweets, search_users, lookup_stored).",
            },
            "username": {
                "type": "string",
                "description": "Twitter username without @ (for user_tweets, user_media).",
            },
            "cursor": {
                "type": "string",
                "description": "Pagination cursor from previous response (for loading more results).",
            },
        },
        "required": ["action"],
    },
}
