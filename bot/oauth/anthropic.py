"""OAuth 2.0 PKCE flow for Claude (Anthropic subscription)."""

import hashlib
import json
import os
import secrets
import webbrowser
from base64 import urlsafe_b64encode
from pathlib import Path
from urllib.parse import urlencode

import httpx

from bot.constants import (
    ANTHROPIC_CLIENT_ID as CLIENT_ID,
    ANTHROPIC_AUTHORIZATION_URL as AUTHORIZATION_URL,
    ANTHROPIC_TOKEN_URL as TOKEN_URL,
    ANTHROPIC_REDIRECT_URI as REDIRECT_URI,
    ANTHROPIC_SCOPES as SCOPES,
)

CREDENTIALS_PATH = Path(__file__).parent.parent.parent / ".credentials.json"


def _generate_pkce():
    verifier_bytes = secrets.token_bytes(32)
    code_verifier = urlsafe_b64encode(verifier_bytes).rstrip(b"=").decode()
    code_challenge = (
        urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    state = urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    return code_verifier, code_challenge, state


def authorize() -> dict:
    """Run OAuth PKCE flow: open browser, get code, exchange for tokens."""
    code_verifier, code_challenge, state = _generate_pkce()

    params = urlencode({
        "code": "true",
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    auth_url = f"{AUTHORIZATION_URL}?{params}"

    print("\nOpening browser for Claude authorization...")
    print(f"\nIf the browser doesn't open, visit:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = input("Paste the authorization code here: ").strip()
    if not code:
        raise SystemExit("Authorization code cannot be empty.")

    # Strip #state suffix if present (Claude callback page may include it)
    if "#" in code:
        code = code[: code.index("#")]

    # Exchange code for tokens
    resp = httpx.post(
        TOKEN_URL,
        json={
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
            "state": state,
        },
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )

    if resp.status_code != 200:
        raise SystemExit(f"Token exchange failed ({resp.status_code}): {resp.text}")

    tokens = resp.json()
    save_credentials(tokens)
    return tokens


def save_credentials(tokens: dict):
    creds = {
        "access_token": tokens["access_token"],
        "refresh_token": tokens.get("refresh_token", ""),
        "expires_in": tokens.get("expires_in", 28800),
    }
    CREDENTIALS_PATH.write_text(json.dumps(creds, indent=2))
    os.chmod(CREDENTIALS_PATH, 0o600)
    print(f"Credentials saved to {CREDENTIALS_PATH}")


def load_credentials() -> dict | None:
    if not CREDENTIALS_PATH.exists():
        return None
    return json.loads(CREDENTIALS_PATH.read_text())


def refresh_token(creds: dict) -> dict:
    """Refresh an expired access token."""
    resp = httpx.post(
        TOKEN_URL,
        json={
            "grant_type": "refresh_token",
            "client_id": CLIENT_ID,
            "refresh_token": creds["refresh_token"],
        },
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")

    tokens = resp.json()
    save_credentials(tokens)
    return tokens

if __name__ == "__main__":
    authorize()