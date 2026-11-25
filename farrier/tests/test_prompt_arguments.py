"""A prompt's `$ARGUMENTS` renders in the form each harness reads."""

from pathlib import Path

from repo_install import install, make_library

PROMPT = (
    '---\ndescription: "Ship a story."\nargument-hint: "<story-id>"\n---\n\n'
    "# Ship story $ARGUMENTS\n\nRun `ship $ARGUMENTS`.\n"
)
CONFIG = "agents:\n  {harness}: true\nprompts:\n  - ship-story\n"


def render(tmp_path: Path, harness: str) -> Path:
    make_library(tmp_path)
    (tmp_path / "agents/library/prompts/ship-story.md").write_text(
        PROMPT, encoding="utf-8"
    )
    code, repo = install(tmp_path, CONFIG.format(harness=harness))
    assert code == 0
    assert install(tmp_path, CONFIG.format(harness=harness), "--check")[0] == 0
    return repo


def test_a_claude_command_keeps_the_arguments_placeholder(tmp_path: Path) -> None:
    repo = render(tmp_path, "claude")
    text = (repo / ".claude/commands/acme-ship-story.md").read_text(encoding="utf-8")
    assert "Run `ship $ARGUMENTS`." in text
    assert 'argument-hint: "<story-id>"' in text


def test_a_copilot_prompt_asks_for_an_input(tmp_path: Path) -> None:
    repo = render(tmp_path, "copilot")
    text = (repo / ".github/prompts/acme-ship-story.prompt.md").read_text(
        encoding="utf-8"
    )
    assert "Run `ship ${input:arguments}`." in text
    assert "$ARGUMENTS" not in text


def test_a_prompt_as_a_skill_names_its_arguments_under_the_heading(
    tmp_path: Path,
) -> None:
    repo = render(tmp_path, "antigravity")
    text = (repo / ".agents/skills/acme-ship-story/SKILL.md").read_text(
        encoding="utf-8"
    )
    assert (
        "# Ship story <arguments>\n\n`<arguments>` stands for the text after this "
        "skill's name when the user runs it: `<story-id>`.\n\nRun `ship <arguments>`."
    ) in text
    assert 'description: "Ship a story."' in text
