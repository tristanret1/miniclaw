"""CLI setup: each service can be configured independently."""

import argparse
import os
import webbrowser
from pathlib import Path

ENV_PATH = Path(__file__).parent / ".env"
DISCORD_DEV_URL = "https://discord.com/developers/applications"


def setup_claude():
    print("\n── Claude Authorization (uses your Claude subscription) ──\n")
    from bot.oauth.anthropic import authorize
    authorize()
    print("Claude setup complete!")


def setup_codex():
    print("\n── Codex Authorization (uses your ChatGPT subscription) ──")
    from bot.oauth.codex import authorize_headless
    authorize_headless()
    print("Codex setup complete!")


def _get_google_client_creds() -> tuple[str, str]:
    """Get Google OAuth client_id/secret — reuse existing or prompt."""
    from bot.google_oauth import load_credentials

    # Check any existing credentials for client_id/secret
    for account in ("life", "work", ""):
        existing = load_credentials(account=account)
        if existing and existing.get("client_id") and existing.get("client_secret"):
            cid, csec = existing["client_id"], existing["client_secret"]
            print(f"Reusing existing client credentials (client_id: {cid[:16]}...)")
            return cid, csec

    print("You need a Google Cloud project with Calendar API enabled.")
    print("Create OAuth 2.0 credentials (Desktop app type) in Google Cloud Console.\n")
    client_id = input("Google OAuth Client ID: ").strip()
    client_secret = input("Google OAuth Client Secret: ").strip()
    return client_id, client_secret


def _authorize_google_account(account: str, label: str):
    """Authorize a single Google account (life or work)."""
    from bot.google_oauth import authorize

    client_id, client_secret = _get_google_client_creds()
    if not client_id or not client_secret:
        print(f"Skipping {label} calendar setup.")
        return

    print(f"\nAuthorizing {label} calendar — sign in with the {label} Google account.")
    authorize(client_id, client_secret, account=account)

    env_content = ENV_PATH.read_text() if ENV_PATH.exists() else ""
    env_key = f"GOOGLE_CALENDAR_{account.upper()}_ID"
    env_vars = {"GOOGLE_CALENDAR_ENABLED": "true"}

    if env_key not in env_content:
        print("Find Calendar ID in: Google Calendar Settings → Integrate calendar → Calendar ID")
        cal_id = input(f"{label.capitalize()} Calendar ID: ").strip()
        if cal_id:
            env_vars[env_key] = cal_id

    _append_env_vars(env_vars, section=f"Google Calendar ({label})")
    print(f"{label.capitalize()} calendar setup complete!")


def setup_google_life():
    print("\n── Google Calendar: Life (personal) ──")
    _authorize_google_account("life", "life")


def setup_google_work():
    print("\n── Google Calendar: Work ──")
    _authorize_google_account("work", "work")


def setup_discord():
    print("\n── Discord Bot Token ──")
    print(f"1. Opening {DISCORD_DEV_URL}")
    print("2. Create an application (or select existing)")
    print("3. Go to 'Bot' tab → 'Reset Token' → copy the token")
    print("4. Enable 'Message Content Intent' under Privileged Gateway Intents")
    print("5. Go to 'OAuth2' → 'URL Generator' → select 'bot' scope")
    print("   → select permissions: Send Messages, Read Message History")
    print("   → use the generated URL to invite the bot to your server")
    webbrowser.open(DISCORD_DEV_URL)
    token = input("\nPaste your Discord Bot Token: ").strip()
    if not token:
        print("Skipping Discord setup.")
        return
    _append_env_vars({"DISCORD_BOT_TOKEN": token}, section="Discord")
    print("Discord setup complete!")


def _append_env_vars(vars: dict[str, str], section: str):
    """Append variables to .env, skipping any that already exist."""
    existing = ""
    if ENV_PATH.exists():
        existing = ENV_PATH.read_text()

    additions = [f"{k}={v}" for k, v in vars.items() if k not in existing]
    if not additions:
        print(f"All {section} vars already in .env, skipping.")
        return

    with open(ENV_PATH, "a") as f:
        f.write(f"\n# {section}\n")
        f.write("\n".join(additions) + "\n")
    os.chmod(ENV_PATH, 0o600)
    print(f"{section} config written to {ENV_PATH}")


SERVICES = {
    "claude": ("Claude (Anthropic OAuth)", setup_claude),
    "codex": ("Codex (OpenAI OAuth)", setup_codex),
    "discord": ("Discord bot token", setup_discord),
    "google-life": ("Google Calendar — life (personal account)", setup_google_life),
    "google-work": ("Google Calendar — work account", setup_google_work),
}


def main():
    targets = ", ".join(SERVICES.keys())
    parser = argparse.ArgumentParser(
        prog="setup",
        description="MiniClaw setup — configure services independently",
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="TARGET",
        help=f"Targets to set up: {targets}, or 'all'",
    )

    args = parser.parse_args()

    if not args.targets:
        parser.print_help()
        print(f"\nAvailable targets:")
        for name, (desc, _) in SERVICES.items():
            print(f"  {name:10s} {desc}")
        print(f"\nExamples:")
        print("  python setup.py claude         # set up Claude only")
        print("  python setup.py discord google # set up Discord + Google")
        print("  python setup.py all            # set up everything")
        return

    for name in args.targets:
        if name == "all":
            for _, (_, fn) in SERVICES.items():
                fn()
            return
        if name not in SERVICES:
            print(f"Unknown target: {name}. Available: {targets}")
            return
        SERVICES[name][1]()


if __name__ == "__main__":
    main()
