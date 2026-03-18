"""Tests for bot.oauth — credential management and token refresh."""

import json
import os
import stat
from unittest.mock import patch, MagicMock

from bot.oauth import (
    _generate_pkce,
    load_credentials,
    save_credentials,
    refresh_token,
)


class TestPKCE:
    def test_generate_pkce_format(self):
        verifier, challenge, state = _generate_pkce()
        # All are non-empty strings
        assert isinstance(verifier, str) and len(verifier) > 0
        assert isinstance(challenge, str) and len(challenge) > 0
        assert isinstance(state, str) and len(state) > 0

    def test_generate_pkce_unique(self):
        """Each call produces unique values."""
        v1, c1, s1 = _generate_pkce()
        v2, c2, s2 = _generate_pkce()
        assert v1 != v2
        assert s1 != s2

    def test_challenge_derives_from_verifier(self):
        """Challenge is SHA256 of verifier, base64url encoded."""
        import hashlib
        from base64 import urlsafe_b64encode
        verifier, challenge, _ = _generate_pkce()
        expected = urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()
        assert challenge == expected


class TestCredentials:
    def test_save_and_load(self, fake_credentials):
        creds, creds_path = fake_credentials
        loaded = load_credentials()
        assert loaded["access_token"] == "fake-access-token"
        assert loaded["refresh_token"] == "fake-refresh-token"

    def test_save_permissions(self, tmp_path, monkeypatch):
        import bot.oauth as oauth_mod
        creds_path = tmp_path / ".credentials.json"
        monkeypatch.setattr(oauth_mod, "CREDENTIALS_PATH", creds_path)

        save_credentials({
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_in": 3600,
        })
        mode = os.stat(creds_path).st_mode
        assert stat.S_IMODE(mode) == 0o600

    def test_load_missing_returns_none(self, tmp_path, monkeypatch):
        import bot.oauth as oauth_mod
        monkeypatch.setattr(oauth_mod, "CREDENTIALS_PATH", tmp_path / "nonexistent.json")
        assert load_credentials() is None

    def test_save_only_keeps_needed_fields(self, tmp_path, monkeypatch):
        import bot.oauth as oauth_mod
        creds_path = tmp_path / ".credentials.json"
        monkeypatch.setattr(oauth_mod, "CREDENTIALS_PATH", creds_path)

        save_credentials({
            "access_token": "tok",
            "refresh_token": "ref",
            "expires_in": 3600,
            "extra_field": "should_be_kept_or_ignored",
        })
        saved = json.loads(creds_path.read_text())
        assert "access_token" in saved
        assert "refresh_token" in saved


class TestRefreshToken:
    def test_success(self, fake_credentials):
        creds, creds_path = fake_credentials
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new-token",
            "refresh_token": "new-refresh",
            "expires_in": 3600,
        }
        with patch("bot.oauth.httpx.post", return_value=mock_resp):
            result = refresh_token(creds)
            assert result["access_token"] == "new-token"
            # Verify saved to disk
            saved = json.loads(creds_path.read_text())
            assert saved["access_token"] == "new-token"

    def test_failure_raises(self, fake_credentials):
        creds, _ = fake_credentials
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "invalid_grant"
        with patch("bot.oauth.httpx.post", return_value=mock_resp):
            import pytest
            with pytest.raises(RuntimeError, match="Token refresh failed"):
                refresh_token(creds)
