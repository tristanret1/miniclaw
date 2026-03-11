"""Claude API calls using OAuth Bearer token (not x-api-key)."""

import httpx
from bot.config import CLAUDE_MODEL, MAX_HISTORY, SYSTEM_PROMPT
from bot.oauth import load_credentials, refresh_token

MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# Per-conversation message history
_sessions: dict[str, list[dict]] = {}


def _get_access_token() -> str:
    creds = load_credentials()
    if not creds:
        raise RuntimeError("Not authenticated. Run: python setup.py")
    return creds["access_token"]


def _call_claude(messages: list[dict]) -> str:
    token = _get_access_token()

    resp = httpx.post(
        MESSAGES_URL,
        json={
            "model": CLAUDE_MODEL,
            "max_tokens": 4096,
            "system": SYSTEM_PROMPT,
            "messages": messages,
        },
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "Content-Type": "application/json",
        },
        timeout=120,
    )

    # Token expired → refresh and retry once
    if resp.status_code == 401:
        creds = load_credentials()
        if creds and creds.get("refresh_token"):
            new_creds = refresh_token(creds)
            resp = httpx.post(
                MESSAGES_URL,
                json={
                    "model": CLAUDE_MODEL,
                    "max_tokens": 4096,
                    "system": SYSTEM_PROMPT,
                    "messages": messages,
                },
                headers={
                    "Authorization": f"Bearer {new_creds['access_token']}",
                    "anthropic-version": "2023-06-01",
                    "anthropic-beta": "oauth-2025-04-20",
                    "Content-Type": "application/json",
                },
                timeout=120,
            )

    if resp.status_code != 200:
        raise RuntimeError(f"Claude API error ({resp.status_code}): {resp.text}")

    return resp.json()["content"][0]["text"]


def get_reply(session_key: str, user_message: str) -> str:
    history = _sessions.setdefault(session_key, [])
    history.append({"role": "user", "content": user_message})

    if len(history) > MAX_HISTORY * 2:
        history[:] = history[-(MAX_HISTORY * 2):]

    reply = _call_claude(history)
    history.append({"role": "assistant", "content": reply})
    return reply
