"""Google Calendar OAuth 2.0 flow and credential management.

Supports per-account credentials: .google_credentials_life.json / _work.json
Falls back to legacy .google_credentials.json for backward compatibility.
"""

import json
import os
import time
from pathlib import Path

from bot.logger import get_logger

log = get_logger("google_oauth")

_PROJECT_ROOT = Path(__file__).parent.parent
CREDENTIALS_PATH = _PROJECT_ROOT / ".google_credentials.json"  # legacy single-file
SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.readonly",
]


def _creds_path(account: str = "") -> Path:
    """Return credentials file path for the given account (life/work/legacy)."""
    if account:
        return _PROJECT_ROOT / f".google_credentials_{account}.json"
    return CREDENTIALS_PATH


def authorize(client_id: str, client_secret: str, account: str = "") -> dict:
    """Run OAuth 2.0 browser flow for Google Calendar access."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, scopes=SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)

    tokens = {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token,
        "expires_at": creds.expiry.timestamp() if creds.expiry else time.time() + 3600,
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": SCOPES,
    }
    save_credentials(tokens, account=account)
    label = f" ({account})" if account else ""
    log.info("Google Calendar OAuth authorized successfully%s", label)
    return tokens


def save_credentials(tokens: dict, account: str = "") -> None:
    """Save OAuth tokens to disk with restricted permissions."""
    path = _creds_path(account)
    path.write_text(json.dumps(tokens, indent=2))
    os.chmod(path, 0o600)
    log.info("Google credentials saved to %s", path)


def load_credentials(account: str = "") -> dict | None:
    """Load OAuth tokens from disk.

    Tries account-specific file first, falls back to legacy single file.
    """
    path = _creds_path(account)
    if not path.exists() and account:
        # Fall back to legacy single credentials file
        path = CREDENTIALS_PATH
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log.error("Failed to load Google credentials from %s: %s", path, e)
        return None


def refresh_credentials(creds: dict, account: str = "") -> dict:
    """Refresh an expired Google access token."""
    import httpx

    resp = httpx.post(
        "https://oauth2.googleapis.com/token",
        data={
            "grant_type": "refresh_token",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "refresh_token": creds["refresh_token"],
        },
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Google token refresh failed ({resp.status_code}): {resp.text}")

    tokens = resp.json()
    updated = {
        **creds,
        "access_token": tokens["access_token"],
        "expires_at": time.time() + tokens.get("expires_in", 3600),
    }
    if "refresh_token" in tokens:
        updated["refresh_token"] = tokens["refresh_token"]

    save_credentials(updated, account=account)
    log.info("Google credentials refreshed successfully")
    return updated


def get_valid_credentials(account: str = "") -> dict | None:
    """Load credentials and auto-refresh if expired. Returns None if unavailable."""
    creds = load_credentials(account)
    if creds is None:
        return None

    expires_at = creds.get("expires_at", 0)
    if time.time() >= expires_at - 60:
        try:
            creds = refresh_credentials(creds, account=account)
        except Exception as e:
            log.error("Failed to refresh Google credentials: %s", e)
            return None

    return creds
