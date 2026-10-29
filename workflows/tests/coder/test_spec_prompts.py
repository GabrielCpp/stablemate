"""The spec section of the dev and docs prompts renders only when the spec pass wrote nodes."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.templates import render
from workhorse_workflows.coder.shared import roles

CODER = Path(roles.__file__).resolve().parent.parent
HEADINGS = {
    "dev/prompts/_dev-inputs.md": "## The book is this story's spec",
    "docs/prompts/document-story.md": "## The book already specifies this story",
}
NODE = "services/app/server.md#contract"


def _rendered(prompt: str, spec_nodes: list[str], tmp_path: Path) -> str:
    repo = tmp_path / "repo"
    skill = repo / ".claude/skills/ostler-okf/SKILL.md"
    skill.parent.mkdir(parents=True)
    _ = skill.write_text("---\nname: ostler-okf\n---\n", encoding="utf-8")
    (repo / ".git").mkdir()
    args = {
        "_node_cwd": str(repo),
        "spec_dir": "specs/STORY-1",
        "spec_nodes": spec_nodes,
        "opening_brief": "",
        "follow_up_title": "",
    }
    return render(prompt, args, CODER)


@pytest.mark.parametrize("prompt", sorted(HEADINGS))
def test_the_spec_section_renders_when_the_spec_pass_wrote_nodes(prompt: str, tmp_path: Path):
    text = _rendered(prompt, [NODE], tmp_path)

    assert HEADINGS[prompt] in text
    assert f"`{NODE}`" in text
    assert "specs/STORY-1/model.md" in text


@pytest.mark.parametrize("prompt", sorted(HEADINGS))
def test_the_spec_section_is_absent_without_spec_nodes(prompt: str, tmp_path: Path):
    text = _rendered(prompt, [], tmp_path)

    assert HEADINGS[prompt] not in text
    assert "model.md" not in text
