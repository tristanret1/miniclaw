# MiniClaw — Repository Guidelines

- Repo: minimal Discord chatbot powered by Claude (Anthropic OAuth 2.0 PKCE)
- Language: Python 3.13+
- No build step; no test framework configured yet.

## Project Structure

- `main.py` — entry point (`python main.py` to run, `python setup.py` for first-time setup)
- `bot/` — core modules:
  - `config.py` — env loading + system prompt assembly from `workspace/` files
  - `client.py` — Discord client, event handlers (`on_ready`, `on_message`)
  - `claude.py` — Claude API calls, per-session message history
  - `oauth.py` — OAuth 2.0 PKCE flow, credential save/load/refresh
- `workspace/` — personality bootstrap files injected into system prompt:
  - `SOUL.md` — behavior principles, language preferences
  - `IDENTITY.md` — agent name, emoji, vibe
- `.credentials.json` — auto-generated OAuth tokens (never commit)
- `.env` — runtime config (never commit)

## Development Commands

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python setup.py        # interactive OAuth + Discord token setup
python main.py         # run the bot
```

## Coding Style

- Standard Python conventions: snake_case for functions/variables, UPPERCASE for constants.
- Use type hints on function signatures.
- Keep the codebase minimal; avoid unnecessary abstractions.
- Credentials go in `.credentials.json` (0o600 perms) or `.env`; never hardcode secrets.

## Key Design Decisions

- Session history is in-memory (`dict` keyed by `{channel_id}:{author_id}`); no persistence across restarts.
- Discord messages are split at 2000 chars (Discord limit).
- OAuth token refresh happens automatically on 401 (single retry).
- System prompt is assembled by reading `workspace/SOUL.md` + `workspace/IDENTITY.md`; falls back to generic prompt if missing.

## Security

- Never commit `.env`, `.credentials.json`, or any real tokens.
- OAuth credentials file must have 0o600 permissions.
