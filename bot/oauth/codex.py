"""Codex (OpenAI) OAuth 2.0 — Device Authorization (headless) + token refresh."""

__all__ = [
    "authorize_headless",
    "save_credentials",
    "load_credentials",
    "refresh_token",
]

import hashlib
import json
import os
import secrets
import time
from base64 import urlsafe_b64encode
from pathlib import Path

import httpx

from bot.constants import (
    CODEX_API_ENDPOINT,
    CODEX_CLIENT_ID as CLIENT_ID,
    CODEX_DEVICE_AUTH_PAGE as DEVICE_AUTH_PAGE,
    CODEX_DEVICE_CODE_URL as DEVICE_CODE_URL,
    CODEX_DEVICE_REDIRECT_URI as DEVICE_REDIRECT_URI,
    CODEX_DEVICE_TOKEN_URL as DEVICE_TOKEN_URL,
    CODEX_TOKEN_URL as TOKEN_URL,
)
from bot.logger import get_logger

log = get_logger("codex_oauth")

CREDENTIALS_PATH = Path(__file__).parent.parent.parent / ".codex_credentials.json"

POLLING_SAFETY_MARGIN = 3  # seconds


# ── JWT helpers ──────────────────────────────────────────────────────────────

def _parse_jwt_claims(token: str) -> dict | None:
    """Parse claims from a JWT without verification."""
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        # Add padding
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        return json.loads(urlsafe_b64encode(
            __import__("base64").urlsafe_b64decode(payload)
        ).decode()) if False else json.loads(
            __import__("base64").urlsafe_b64decode(payload).decode()
        )
    except Exception:
        return None


def _extract_account_id(tokens: dict) -> str | None:
    """Extract ChatGPT account ID from JWT claims."""
    for token_key in ("id_token", "access_token"):
        token = tokens.get(token_key)
        if not token:
            continue
        claims = _parse_jwt_claims(token)
        if not claims:
            continue
        account_id = (
            claims.get("chatgpt_account_id")
            or (claims.get("https://api.openai.com/auth") or {}).get("chatgpt_account_id")
        )
        if account_id:
            return account_id
        orgs = claims.get("organizations")
        if orgs and isinstance(orgs, list) and len(orgs) > 0:
            return orgs[0].get("id")
    return None


# ── Device Authorization Flow (headless) ─────────────────────────────────────

def authorize_headless() -> dict:
    """Run headless device authorization flow.

    1. Request device code from OpenAI
    2. Display user code + URL for the user to visit
    3. Poll for authorization
    4. Exchange code for tokens
    """
    # Step 1: Get device code
    resp = httpx.post(
        DEVICE_CODE_URL,
        json={"client_id": CLIENT_ID},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Device auth initiation failed ({resp.status_code}): {resp.text}")

    device_data = resp.json()
    device_auth_id = device_data["device_auth_id"]
    user_code = device_data["user_code"]
    interval = max(int(device_data.get("interval", 5)), 1)

    # Step 2: Display instructions
    print(f"\n── Codex Authorization (headless) ──")
    print(f"\n  Visit: {DEVICE_AUTH_PAGE}")
    print(f"  Enter code: {user_code}\n")

    # Step 3: Poll for authorization
    timeout_at = time.time() + 300  # 5 minute timeout
    while time.time() < timeout_at:
        time.sleep(interval + POLLING_SAFETY_MARGIN)

        poll_resp = httpx.post(
            DEVICE_TOKEN_URL,
            json={
                "device_auth_id": device_auth_id,
                "user_code": user_code,
            },
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if poll_resp.status_code == 200:
            poll_data = poll_resp.json()
            authorization_code = poll_data["authorization_code"]
            code_verifier = poll_data["code_verifier"]

            # Step 4: Exchange for tokens
            token_resp = httpx.post(
                TOKEN_URL,
                content=__import__("urllib.parse", fromlist=["urlencode"]).urlencode({
                    "grant_type": "authorization_code",
                    "code": authorization_code,
                    "redirect_uri": DEVICE_REDIRECT_URI,
                    "client_id": CLIENT_ID,
                    "code_verifier": code_verifier,
                }),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            if token_resp.status_code != 200:
                raise RuntimeError(f"Token exchange failed ({token_resp.status_code}): {token_resp.text}")

            tokens = token_resp.json()
            account_id = _extract_account_id(tokens)

            creds = {
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "expires_at": time.time() + (tokens.get("expires_in", 3600)),
                "account_id": account_id,
            }
            save_credentials(creds)
            print("Codex authorization successful!")
            return creds

        # 403/404 = still waiting, anything else = error
        if poll_resp.status_code not in (403, 404):
            raise RuntimeError(f"Device auth failed ({poll_resp.status_code}): {poll_resp.text}")

    raise RuntimeError("Device authorization timed out (5 minutes)")


# ── Credential management ────────────────────────────────────────────────────

def save_credentials(creds: dict) -> None:
    CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))
    os.chmod(CREDENTIALS_PATH, 0o600)
    log.info("codex credentials saved to %s", CREDENTIALS_PATH)


def load_credentials() -> dict | None:
    if not CREDENTIALS_PATH.exists():
        return None
    try:
        return json.loads(CREDENTIALS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def refresh_token(creds: dict) -> dict:
    """Refresh an expired Codex access token."""
    from urllib.parse import urlencode

    resp = httpx.post(
        TOKEN_URL,
        content=urlencode({
            "grant_type": "refresh_token",
            "refresh_token": creds["refresh_token"],
            "client_id": CLIENT_ID,
        }),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Codex token refresh failed ({resp.status_code}): {resp.text}")

    tokens = resp.json()
    account_id = _extract_account_id(tokens) or creds.get("account_id")
    new_creds = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", creds["refresh_token"]),
        "expires_at": time.time() + (tokens.get("expires_in", 3600)),
        "account_id": account_id,
    }
    save_credentials(new_creds)
    return new_creds
