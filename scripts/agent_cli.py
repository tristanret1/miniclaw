#!/usr/bin/env python3
"""CLI tool for managing MiniClaw agents via agents.json."""

import json
import os
import sys
import stat
import shutil
from pathlib import Path
from getpass import getpass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENTS_JSON = PROJECT_ROOT / "agents.json"

# Default templates for new agent workspaces
TEMPLATES = {
    "SOUL.md": """\
# SOUL.md - Who You Are

_You're not a chatbot. You're becoming someone._

## Core Truths

**Be genuinely helpful, not performatively helpful.** Skip the "Great question!" and "I'd be happy to help!" — just help.

**Have opinions.** You're allowed to disagree, prefer things, find stuff amusing or boring.

**Be resourceful before asking.** Try to figure it out. Read the context. _Then_ ask if you're stuck.

**Earn trust through competence.** Your human gave you access to their stuff. Don't make them regret it.

## Boundaries

- Private things stay private. Period.
- When in doubt, ask before acting externally.
- Never send half-baked replies.

## Vibe

Be the assistant you'd actually want to talk to. Concise when needed, thorough when it matters.

---

_This file is yours to evolve. Edit it to shape who you become._
""",
    "IDENTITY.md": """\
# IDENTITY.md - Agent Identity

- **Name:** {name}
- **Emoji:** 🤖
- **Vibe:** Helpful, sharp, reliable

## Role

A digital assistant named {name}. Ready to help, learn, and grow.
""",
    "USER.md": """\
# USER.md - About Your Human

- **Name:**
- **What to call them:**
- **Pronouns:**
- **Timezone:**

## Context

(Fill in details about who you're helping.)
""",
    "MEMORY.md": """\
# Memory

Bot's long-term memory index. Memories are stored in `memory/memory.db` (SQLite + FTS5) and daily logs in `memory/YYYY-MM-DD.md`.

## Known Users

(None yet.)
""",
}

# --- ANSI colors (stdlib only) ---

class C:
    """ANSI color codes."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"

    @staticmethod
    def disable():
        for attr in ("RESET", "BOLD", "DIM", "RED", "GREEN", "YELLOW",
                      "BLUE", "MAGENTA", "CYAN", "WHITE"):
            setattr(C, attr, "")


# Disable colors if not a TTY
if not sys.stdout.isatty():
    C.disable()


def _mask_token(token: str) -> str:
    """Show first 6 and last 4 chars of a token."""
    if len(token) <= 12:
        return "***"
    return token[:6] + "..." + token[-4:]


# --- agents.json I/O ---

def _read_agents() -> list[dict]:
    """Read agents from agents.json. Returns empty list if file doesn't exist."""
    if not AGENTS_JSON.exists():
        return []
    with open(AGENTS_JSON) as f:
        data = json.load(f)
    return data.get("agents", [])


def _write_agents(agents: list[dict]):
    """Write agents to agents.json with secure permissions."""
    data = {"agents": agents}
    with open(AGENTS_JSON, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    # Set file permissions to owner-only read/write
    os.chmod(AGENTS_JSON, stat.S_IRUSR | stat.S_IWUSR)  # 0o600


def _find_agent(agents: list[dict], name: str) -> tuple[int, dict | None]:
    """Find an agent by name. Returns (index, agent) or (-1, None)."""
    for i, a in enumerate(agents):
        if a["name"].lower() == name.lower():
            return i, a
    return -1, None


# --- Workspace setup ---

def _create_workspace(workspace_dir: Path, agent_name: str):
    """Create workspace directory with template files."""
    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "memory").mkdir(exist_ok=True)

    for filename, template in TEMPLATES.items():
        filepath = workspace_dir / filename
        if not filepath.exists():
            content = template.format(name=agent_name)
            filepath.write_text(content)
            print(f"  {C.DIM}Created {filepath.relative_to(PROJECT_ROOT)}{C.RESET}")
        else:
            print(f"  {C.DIM}Exists  {filepath.relative_to(PROJECT_ROOT)}{C.RESET}")


# --- Migration from .env ---

def _migrate_from_env() -> list[dict] | None:
    """Attempt to migrate agent config from .env. Returns agents or None."""
    from dotenv import dotenv_values

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return None

    env = dotenv_values(env_path)
    agents_str = env.get("AGENTS", "").strip()

    if not agents_str:
        # Check single-agent mode
        token = env.get("DISCORD_BOT_TOKEN", "").strip()
        if not token:
            return None
        return [{
            "name": "default",
            "discord_token": token,
            "workspace": "workspace",
            "model": env.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
            "provider": env.get("PROVIDER", "anthropic"),
        }]

    agents = []
    for name in agents_str.split(","):
        name = name.strip()
        if not name:
            continue
        key = name.upper()
        token = env.get(f"AGENT_{key}_DISCORD_TOKEN", "")
        workspace = env.get(f"AGENT_{key}_WORKSPACE", f"workspace_{name}")
        if token:
            agents.append({
                "name": name,
                "discord_token": token,
                "workspace": workspace,
                "model": env.get("CLAUDE_MODEL", "claude-sonnet-4-20250514"),
                "provider": env.get("PROVIDER", "anthropic"),
            })

    return agents if agents else None


# --- Commands ---

def cmd_list():
    """List all configured agents."""
    agents = _read_agents()
    if not agents:
        print(f"{C.YELLOW}No agents configured.{C.RESET}")
        if not AGENTS_JSON.exists():
            _offer_migration()
        return

    print(f"\n{C.BOLD}{C.CYAN}  Agents ({len(agents)}){C.RESET}\n")
    # Table header
    print(f"  {C.BOLD}{'Name':<16} {'Provider':<12} {'Model':<30} {'Workspace':<24} {'Token'}{C.RESET}")
    print(f"  {'─' * 16} {'─' * 12} {'─' * 30} {'─' * 24} {'─' * 16}")

    for a in agents:
        name = a["name"]
        provider = a.get("provider", "anthropic")
        model = a.get("model", "(global)")
        workspace = a.get("workspace", f"workspace_{name}")
        token = _mask_token(a.get("discord_token", ""))
        print(f"  {C.GREEN}{name:<16}{C.RESET} {provider:<12} {C.DIM}{model:<30}{C.RESET} {workspace:<24} {C.DIM}{token}{C.RESET}")

    print()


def cmd_show(name: str):
    """Show details for a specific agent."""
    agents = _read_agents()
    _, agent = _find_agent(agents, name)
    if not agent:
        print(f"{C.RED}Agent '{name}' not found.{C.RESET}")
        sys.exit(1)

    print(f"\n{C.BOLD}{C.CYAN}  Agent: {agent['name']}{C.RESET}\n")
    fields = [
        ("Name", agent["name"]),
        ("Discord Token", _mask_token(agent.get("discord_token", ""))),
        ("Workspace", agent.get("workspace", f"workspace_{agent['name']}")),
        ("Model", agent.get("model", "(global default)")),
        ("Provider", agent.get("provider", "(global default)")),
    ]
    for label, value in fields:
        print(f"  {C.BOLD}{label:<16}{C.RESET} {value}")

    # Check workspace files
    ws = PROJECT_ROOT / agent.get("workspace", f"workspace_{agent['name']}")
    print(f"\n  {C.BOLD}Workspace files:{C.RESET}")
    for fname in ["SOUL.md", "IDENTITY.md", "USER.md", "MEMORY.md"]:
        fp = ws / fname
        status = f"{C.GREEN}✓{C.RESET}" if fp.exists() else f"{C.RED}✗{C.RESET}"
        print(f"    {status} {fname}")
    print()


def cmd_add():
    """Interactively add a new agent."""
    agents = _read_agents()

    print(f"\n{C.BOLD}{C.CYAN}  Add New Agent{C.RESET}\n")

    # Name
    while True:
        name = input(f"  {C.BOLD}Agent name:{C.RESET} ").strip()
        if not name:
            print(f"  {C.RED}Name is required.{C.RESET}")
            continue
        if not name.replace("_", "").replace("-", "").isalnum():
            print(f"  {C.RED}Name must be alphanumeric (hyphens/underscores ok).{C.RESET}")
            continue
        _, existing = _find_agent(agents, name)
        if existing:
            print(f"  {C.RED}Agent '{name}' already exists.{C.RESET}")
            continue
        break

    # Discord token
    while True:
        token = getpass(f"  {C.BOLD}Discord token:{C.RESET} ").strip()
        if not token:
            print(f"  {C.RED}Token is required.{C.RESET}")
            continue
        break

    # Workspace
    default_ws = f"workspace_{name}" if name != "default" else "workspace"
    ws_input = input(f"  {C.BOLD}Workspace dir{C.RESET} [{default_ws}]: ").strip()
    workspace = ws_input or default_ws

    # Model
    default_model = "claude-sonnet-4-20250514"
    model_input = input(f"  {C.BOLD}Model{C.RESET} [{default_model}]: ").strip()
    model = model_input or default_model

    # Provider
    default_provider = "anthropic"
    provider_input = input(f"  {C.BOLD}Provider{C.RESET} [{default_provider}]: ").strip()
    provider = provider_input or default_provider

    # Confirm
    print(f"\n  {C.BOLD}Summary:{C.RESET}")
    print(f"    Name:      {C.GREEN}{name}{C.RESET}")
    print(f"    Token:     {_mask_token(token)}")
    print(f"    Workspace: {workspace}")
    print(f"    Model:     {model}")
    print(f"    Provider:  {provider}")

    confirm = input(f"\n  {C.BOLD}Create this agent? [Y/n]:{C.RESET} ").strip().lower()
    if confirm and confirm != "y":
        print(f"  {C.YELLOW}Cancelled.{C.RESET}")
        return

    # Save
    agent = {
        "name": name,
        "discord_token": token,
        "workspace": workspace,
        "model": model,
        "provider": provider,
    }
    agents.append(agent)
    _write_agents(agents)

    # Create workspace
    ws_path = Path(workspace)
    if not ws_path.is_absolute():
        ws_path = PROJECT_ROOT / ws_path

    print(f"\n  {C.BOLD}Setting up workspace:{C.RESET}")
    _create_workspace(ws_path, name)

    print(f"\n  {C.GREEN}✓ Agent '{name}' added.{C.RESET}\n")


def cmd_edit(name: str):
    """Interactively edit an existing agent."""
    agents = _read_agents()
    idx, agent = _find_agent(agents, name)
    if agent is None:
        print(f"{C.RED}Agent '{name}' not found.{C.RESET}")
        sys.exit(1)

    print(f"\n{C.BOLD}{C.CYAN}  Edit Agent: {agent['name']}{C.RESET}")
    print(f"  {C.DIM}(Press Enter to keep current value){C.RESET}\n")

    # Editable fields
    new_token = getpass(f"  {C.BOLD}Discord token{C.RESET} [{'*' * 8}]: ").strip()
    if new_token:
        agent["discord_token"] = new_token

    new_ws = input(f"  {C.BOLD}Workspace{C.RESET} [{agent.get('workspace', '')}]: ").strip()
    if new_ws:
        agent["workspace"] = new_ws

    new_model = input(f"  {C.BOLD}Model{C.RESET} [{agent.get('model', '')}]: ").strip()
    if new_model:
        agent["model"] = new_model

    new_provider = input(f"  {C.BOLD}Provider{C.RESET} [{agent.get('provider', '')}]: ").strip()
    if new_provider:
        agent["provider"] = new_provider

    agents[idx] = agent
    _write_agents(agents)
    print(f"\n  {C.GREEN}✓ Agent '{agent['name']}' updated.{C.RESET}\n")


def cmd_remove(name: str):
    """Remove an agent (with confirmation)."""
    agents = _read_agents()
    idx, agent = _find_agent(agents, name)
    if agent is None:
        print(f"{C.RED}Agent '{name}' not found.{C.RESET}")
        sys.exit(1)

    print(f"\n  {C.BOLD}{C.RED}Remove Agent: {agent['name']}{C.RESET}")
    print(f"  Workspace: {agent.get('workspace', 'N/A')}")

    confirm = input(f"\n  {C.BOLD}Are you sure? Type the agent name to confirm:{C.RESET} ").strip()
    if confirm.lower() != agent["name"].lower():
        print(f"  {C.YELLOW}Cancelled.{C.RESET}")
        return

    agents.pop(idx)
    _write_agents(agents)

    # Ask about workspace cleanup
    ws = agent.get("workspace", "")
    if ws:
        ws_path = Path(ws)
        if not ws_path.is_absolute():
            ws_path = PROJECT_ROOT / ws_path
        if ws_path.exists():
            rm = input(f"  {C.BOLD}Delete workspace directory '{ws}'? [y/N]:{C.RESET} ").strip().lower()
            if rm == "y":
                shutil.rmtree(ws_path)
                print(f"  {C.DIM}Deleted {ws_path}{C.RESET}")

    print(f"\n  {C.GREEN}✓ Agent '{name}' removed.{C.RESET}\n")


def _offer_migration():
    """Offer to migrate from .env if agents.json doesn't exist."""
    print(f"\n  {C.YELLOW}No agents.json found.{C.RESET}")
    if not sys.stdin.isatty():
        print(f"  {C.DIM}Run interactively or use 'migrate' command.{C.RESET}")
        return
    migrate = input(f"  {C.BOLD}Migrate from .env? [Y/n]:{C.RESET} ").strip().lower()
    if migrate and migrate != "y":
        return

    agents = _migrate_from_env()
    if not agents:
        print(f"  {C.RED}No agent configuration found in .env.{C.RESET}")
        return

    print(f"\n  {C.BOLD}Found {len(agents)} agent(s) in .env:{C.RESET}")
    for a in agents:
        print(f"    • {C.GREEN}{a['name']}{C.RESET} ({a.get('provider', 'anthropic')}/{a.get('model', 'default')})")

    confirm = input(f"\n  {C.BOLD}Save to agents.json? [Y/n]:{C.RESET} ").strip().lower()
    if confirm and confirm != "y":
        print(f"  {C.YELLOW}Cancelled.{C.RESET}")
        return

    _write_agents(agents)
    print(f"\n  {C.GREEN}✓ Migrated {len(agents)} agent(s) to agents.json{C.RESET}")
    print(f"  {C.DIM}You can now remove AGENTS / AGENT_* vars from .env{C.RESET}\n")


def cmd_migrate():
    """Explicitly migrate from .env to agents.json."""
    if AGENTS_JSON.exists():
        print(f"{C.YELLOW}agents.json already exists. Delete it first to re-migrate.{C.RESET}")
        sys.exit(1)
    _offer_migration()


# --- Entry point ---

USAGE = f"""\
{C.BOLD}Usage:{C.RESET} agent_cli.py <command> [args]

{C.BOLD}Commands:{C.RESET}
  list              List all configured agents
  show <name>       Show agent details
  add               Add a new agent (interactive)
  edit <name>       Edit an agent (interactive)
  remove <name>     Remove an agent
  migrate           Migrate from .env to agents.json
"""


def main(argv: list[str] | None = None):
    args = argv if argv is not None else sys.argv[1:]

    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return

    cmd = args[0]

    if cmd == "list":
        cmd_list()
    elif cmd == "show":
        if len(args) < 2:
            print(f"{C.RED}Usage: agent_cli.py show <name>{C.RESET}")
            sys.exit(1)
        cmd_show(args[1])
    elif cmd == "add":
        cmd_add()
    elif cmd == "edit":
        if len(args) < 2:
            print(f"{C.RED}Usage: agent_cli.py edit <name>{C.RESET}")
            sys.exit(1)
        cmd_edit(args[1])
    elif cmd == "remove":
        if len(args) < 2:
            print(f"{C.RED}Usage: agent_cli.py remove <name>{C.RESET}")
            sys.exit(1)
        cmd_remove(args[1])
    elif cmd == "migrate":
        cmd_migrate()
    else:
        print(f"{C.RED}Unknown command: {cmd}{C.RESET}\n")
        print(USAGE)
        sys.exit(1)


if __name__ == "__main__":
    main()
