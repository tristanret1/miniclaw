"""Skill system — load, parse, and inject Clawhub-compatible SKILL.md files."""

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from bot.logger import get_logger

log = get_logger("skills")

# Max SKILL.md file size (256 KB, same as openclaw)
MAX_SKILL_FILE_BYTES = 256_000


@dataclass
class Skill:
    """Parsed skill from a SKILL.md file."""

    name: str
    description: str
    body: str  # Markdown instructions (after frontmatter)
    file_path: str = ""
    user_invocable: bool = True
    model_invocable: bool = True  # inverse of disable-model-invocation
    emoji: str = ""
    requires_bins: list[str] = field(default_factory=list)
    requires_any_bins: list[str] = field(default_factory=list)
    requires_env: list[str] = field(default_factory=list)


def _parse_skill_md(path: Path) -> Skill | None:
    """Parse a SKILL.md file into a Skill object.

    Format: YAML frontmatter (between --- markers) + Markdown body.
    """
    if not path.is_file():
        return None

    if path.stat().st_size > MAX_SKILL_FILE_BYTES:
        log.warning("skill file too large, skipping: %s (%d bytes)", path, path.stat().st_size)
        return None

    text = path.read_text(encoding="utf-8")

    # Split frontmatter and body
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)", text, re.DOTALL)
    if not match:
        log.warning("no YAML frontmatter found in %s", path)
        return None

    frontmatter_str, body = match.group(1), match.group(2).strip()

    try:
        fm = yaml.safe_load(frontmatter_str) or {}
    except yaml.YAMLError as e:
        log.warning("invalid YAML in %s: %s", path, e)
        return None

    name = fm.get("name", "")
    description = fm.get("description", "")
    if not name or not description:
        log.warning("skill missing name or description: %s", path)
        return None

    # Parse openclaw metadata
    metadata = fm.get("metadata", {})
    if isinstance(metadata, str):
        # metadata field might be a JSON string
        try:
            import json
            metadata = json.loads(metadata)
        except (json.JSONDecodeError, TypeError):
            metadata = {}

    oc_meta = metadata.get("openclaw", {}) if isinstance(metadata, dict) else {}

    emoji = oc_meta.get("emoji", "")
    requires = oc_meta.get("requires", {})
    requires_bins = requires.get("bins", []) if isinstance(requires, dict) else []
    requires_any_bins = requires.get("anyBins", []) if isinstance(requires, dict) else []
    requires_env = requires.get("env", []) if isinstance(requires, dict) else []

    user_invocable = fm.get("user-invocable", True)
    model_invocable = not fm.get("disable-model-invocation", False)

    return Skill(
        name=name,
        description=description,
        body=body,
        file_path=str(path),
        user_invocable=bool(user_invocable),
        model_invocable=bool(model_invocable),
        emoji=emoji,
        requires_bins=requires_bins,
        requires_any_bins=requires_any_bins,
        requires_env=requires_env,
    )


def _check_requirements(skill: Skill) -> bool:
    """Check if a skill's runtime requirements are met."""
    import os

    # Check required binaries
    for bin_name in skill.requires_bins:
        if not shutil.which(bin_name):
            log.warning("skill '%s' requires binary '%s' not found, skipping", skill.name, bin_name)
            return False

    # Check any-of binaries
    if skill.requires_any_bins:
        if not any(shutil.which(b) for b in skill.requires_any_bins):
            log.warning(
                "skill '%s' requires at least one of %s, none found, skipping",
                skill.name, skill.requires_any_bins,
            )
            return False

    # Check required env vars
    for env_var in skill.requires_env:
        if not os.environ.get(env_var):
            log.warning("skill '%s' requires env var '%s' not set, skipping", skill.name, env_var)
            return False

    return True


def load_skills(skills_dir: Path) -> list[Skill]:
    """Scan skills_dir for subdirectories containing SKILL.md and return parsed skills.

    Only skills whose requirements are met are included.
    """
    if not skills_dir.is_dir():
        log.info("skills directory not found: %s", skills_dir)
        return []

    skills: list[Skill] = []

    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        skill_file = child / "SKILL.md"
        skill = _parse_skill_md(skill_file)
        if skill is None:
            continue
        if not _check_requirements(skill):
            continue
        skills.append(skill)
        log.info("loaded skill: %s %s", skill.emoji or "·", skill.name)

    log.info("loaded %d skill(s) from %s", len(skills), skills_dir)
    return skills


def build_skills_prompt(skills: list[Skill]) -> str:
    """Format model-invocable skills as an XML block for the system prompt."""
    model_skills = [s for s in skills if s.model_invocable]
    if not model_skills:
        return ""

    lines = ["<available-skills>"]
    for s in model_skills:
        emoji_attr = f' emoji="{s.emoji}"' if s.emoji else ""
        invocable_attr = ' user-invocable="true"' if s.user_invocable else ""
        lines.append(f'<skill name="{s.name}" description="{s.description}"{emoji_attr}{invocable_attr}>')
        lines.append(s.body)
        lines.append("</skill>")
    lines.append("</available-skills>")

    return "\n".join(lines)


def build_skill_command_list(skills: list[Skill]) -> str:
    """Build a user-facing list of available skill slash commands."""
    user_skills = [s for s in skills if s.user_invocable]
    if not user_skills:
        return "No skills available."

    lines = ["**Available skills:**"]
    for s in user_skills:
        prefix = f"{s.emoji} " if s.emoji else ""
        lines.append(f"  `/{s.name}` — {prefix}{s.description}")
    return "\n".join(lines)


def match_skill_command(text: str, skills: list[Skill]) -> tuple[Skill, str] | None:
    """Check if text starts with /skill-name and return (skill, remaining_args).

    Only matches user-invocable skills.
    """
    if not text.startswith("/"):
        return None

    # Extract command name (first word after /)
    parts = text[1:].split(None, 1)
    if not parts:
        return None

    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    for skill in skills:
        if not skill.user_invocable:
            continue
        # Match by name (case-insensitive, allowing underscores for hyphens)
        skill_cmd = skill.name.lower().replace("-", "_")
        if cmd == skill.name.lower() or cmd == skill_cmd:
            return (skill, args)

    return None


def build_skill_user_message(skill: Skill, args: str) -> str:
    """Build a user message that injects skill context for Claude.

    When a user triggers a skill via /command, we prepend the skill's
    instructions so Claude knows how to handle the request.
    """
    parts = [f"[Skill: {skill.name}]", "", skill.body, ""]
    if args:
        parts.append(f"User request: {args}")
    else:
        parts.append("User request: (no additional input — use the skill's default behavior)")
    return "\n".join(parts)
