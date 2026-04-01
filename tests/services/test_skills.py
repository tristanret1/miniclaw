"""Tests for bot.skills — skill parsing, loading, and command matching."""

from pathlib import Path

import pytest

from bot.skills import (
    Skill,
    _parse_skill_md,
    _check_requirements,
    load_skills,
    build_skills_prompt,
    build_skill_command_list,
    match_skill_command,
    build_skill_user_message,
)


@pytest.fixture
def sample_skill_dir(tmp_path):
    """Create a sample skills directory with test skills."""
    skill_dir = tmp_path / "skills" / "greeting"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: greeting\n"
        "description: Say hello in a fun way\n"
        "user-invocable: true\n"
        "---\n"
        "When triggered, greet the user warmly.\n"
    )
    return tmp_path / "skills"


@pytest.fixture
def sample_skill():
    return Skill(
        name="greeting",
        description="Say hello in a fun way",
        body="When triggered, greet the user warmly.",
        user_invocable=True,
        model_invocable=True,
    )


class TestParseSkillMd:
    def test_valid_skill(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(
            "---\n"
            "name: test-skill\n"
            "description: A test skill\n"
            "---\n"
            "Do the thing.\n"
        )
        skill = _parse_skill_md(f)
        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill"
        assert skill.body == "Do the thing."
        assert skill.user_invocable is True
        assert skill.model_invocable is True

    def test_missing_frontmatter(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("No frontmatter here.\n")
        assert _parse_skill_md(f) is None

    def test_missing_name(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(
            "---\n"
            "description: No name\n"
            "---\n"
            "body\n"
        )
        assert _parse_skill_md(f) is None

    def test_missing_description(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(
            "---\n"
            "name: test\n"
            "---\n"
            "body\n"
        )
        assert _parse_skill_md(f) is None

    def test_nonexistent_file(self, tmp_path):
        assert _parse_skill_md(tmp_path / "nope.md") is None

    def test_disable_model_invocation(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(
            "---\n"
            "name: internal\n"
            "description: Internal only\n"
            "disable-model-invocation: true\n"
            "---\n"
            "body\n"
        )
        skill = _parse_skill_md(f)
        assert skill is not None
        assert skill.model_invocable is False

    def test_user_invocable_false(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(
            "---\n"
            "name: auto-only\n"
            "description: Only for model\n"
            "user-invocable: false\n"
            "---\n"
            "body\n"
        )
        skill = _parse_skill_md(f)
        assert skill is not None
        assert skill.user_invocable is False

    def test_openclaw_metadata(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text(
            "---\n"
            "name: weather\n"
            "description: Get weather\n"
            "metadata:\n"
            "  openclaw:\n"
            "    emoji: ☀️\n"
            "    requires:\n"
            "      bins:\n"
            "        - curl\n"
            "---\n"
            "body\n"
        )
        skill = _parse_skill_md(f)
        assert skill is not None
        assert skill.emoji == "☀️"
        assert skill.requires_bins == ["curl"]

    def test_file_too_large(self, tmp_path):
        f = tmp_path / "SKILL.md"
        f.write_text("x" * 300_000)
        assert _parse_skill_md(f) is None


class TestCheckRequirements:
    def test_no_requirements(self, sample_skill):
        assert _check_requirements(sample_skill) is True

    def test_missing_binary(self):
        skill = Skill(
            name="test", description="test", body="body",
            requires_bins=["nonexistent_binary_xyz_12345"],
        )
        assert _check_requirements(skill) is False

    def test_existing_binary(self):
        skill = Skill(
            name="test", description="test", body="body",
            requires_bins=["python3"],
        )
        assert _check_requirements(skill) is True

    def test_missing_env(self, monkeypatch):
        monkeypatch.delenv("SOME_RARE_VAR_XYZ", raising=False)
        skill = Skill(
            name="test", description="test", body="body",
            requires_env=["SOME_RARE_VAR_XYZ"],
        )
        assert _check_requirements(skill) is False


class TestLoadSkills:
    def test_loads_from_directory(self, sample_skill_dir):
        skills = load_skills(sample_skill_dir)
        assert len(skills) == 1
        assert skills[0].name == "greeting"

    def test_nonexistent_dir(self, tmp_path):
        skills = load_skills(tmp_path / "nope")
        assert skills == []

    def test_skips_non_directories(self, tmp_path):
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        (skills_dir / "stray_file.txt").write_text("not a skill")
        skills = load_skills(skills_dir)
        assert skills == []

    def test_multiple_skills(self, tmp_path):
        skills_dir = tmp_path / "skills"
        for name in ["alpha", "beta"]:
            d = skills_dir / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                f"---\nname: {name}\ndescription: {name} skill\n---\nbody\n"
            )
        skills = load_skills(skills_dir)
        assert len(skills) == 2
        assert [s.name for s in skills] == ["alpha", "beta"]


class TestBuildSkillsPrompt:
    def test_empty_skills(self):
        assert build_skills_prompt([]) == ""

    def test_generates_catalog(self, sample_skill):
        result = build_skills_prompt([sample_skill])
        assert "<available-skills>" in result
        assert "**greeting**" in result
        assert "Say hello in a fun way" in result  # description included
        assert "skills/greeting/SKILL.md" in result  # location included
        assert sample_skill.body not in result  # body NOT included

    def test_excludes_non_model_invocable(self):
        skill = Skill(name="s", description="d", body="b", model_invocable=False)
        assert build_skills_prompt([skill]) == ""


class TestBuildSkillCommandList:
    def test_no_skills(self):
        assert "No skills" in build_skill_command_list([])

    def test_lists_skills(self, sample_skill):
        result = build_skill_command_list([sample_skill])
        assert "/greeting" in result
        assert "Say hello" in result

    def test_excludes_non_user_invocable(self):
        skill = Skill(name="s", description="d", body="b", user_invocable=False)
        assert "No skills" in build_skill_command_list([skill])


class TestMatchSkillCommand:
    def test_matches_command(self, sample_skill):
        result = match_skill_command("/greeting hello", [sample_skill])
        assert result is not None
        skill, args = result
        assert skill.name == "greeting"
        assert args == "hello"

    def test_no_args(self, sample_skill):
        result = match_skill_command("/greeting", [sample_skill])
        assert result is not None
        _, args = result
        assert args == ""

    def test_no_match(self, sample_skill):
        assert match_skill_command("/unknown", [sample_skill]) is None

    def test_not_a_command(self, sample_skill):
        assert match_skill_command("hello", [sample_skill]) is None

    def test_case_insensitive(self, sample_skill):
        result = match_skill_command("/GREETING hi", [sample_skill])
        assert result is not None

    def test_hyphen_underscore(self):
        skill = Skill(name="snow-forecast", description="d", body="b")
        result = match_skill_command("/snow_forecast", [skill])
        assert result is not None

    def test_skips_non_user_invocable(self):
        skill = Skill(name="internal", description="d", body="b", user_invocable=False)
        assert match_skill_command("/internal", [skill]) is None


class TestBuildSkillUserMessage:
    def test_with_args(self, sample_skill):
        msg = build_skill_user_message(sample_skill, "world")
        assert "[Skill: greeting]" in msg
        assert "greet the user warmly" in msg
        assert "User request: world" in msg

    def test_no_args(self, sample_skill):
        msg = build_skill_user_message(sample_skill, "")
        assert "default behavior" in msg
