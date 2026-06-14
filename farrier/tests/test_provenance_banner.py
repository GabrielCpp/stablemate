"""Generated skills are stamped with their library source in the `metadata` field.

A generated skill is a *copy* of a library SKILL.md. Without a marker an agent edits
the copy and loses the change on the next `make agent-install`. So each generated
SKILL.md names its source of truth in the openskill `metadata` field
(openskill.sh/docs/creators/skill-format).

Prompts/commands and aggregated instruction files are NOT skills and are left
untouched — no metadata, no comment, nothing added.

    ./.venv/bin/python -m pytest tests/test_provenance_banner.py
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from farrier.install import (
    Renderer,
    Source,
    library_source_path,
    skill_metadata_block,
)


def _skill_source(tmp_path: Path, body: str = "# Go\nUse for Go work.\n") -> Source:
    skill_file = tmp_path / "library" / "skills" / "go" / "go-qa" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(textwrap.dedent(body), encoding="utf-8")
    return Source(
        kind="skill", path=skill_file, rel="go/go-qa/SKILL.md", id="go/go-qa"
    )


def test_library_source_path_anchors_at_library(tmp_path):
    source = _skill_source(tmp_path)
    # Machine-independent: starts at the `library/` segment, drops the abs prefix.
    assert library_source_path(source) == "library/skills/go/go-qa/SKILL.md"


def test_metadata_block_names_source_and_warns(tmp_path):
    block = skill_metadata_block(_skill_source(tmp_path))
    assert block.startswith("metadata:\n")
    assert "  generated_by: farrier\n" in block
    assert "  source: library/skills/go/go-qa/SKILL.md\n" in block
    assert "  do_not_edit:" in block
    assert "make agent-install" in block


def _renderer_with(tmp_path: Path, skills=None, prompts=None) -> Renderer:
    return Renderer(
        repo=tmp_path,
        prefix="demo",
        repo_config={},
        template_values={},
        skills=skills or [],
        prompts=prompts or [],
    )


def test_generated_skill_carries_metadata_in_front_matter(tmp_path):
    source = _skill_source(tmp_path)
    renderer = _renderer_with(tmp_path, skills=[source])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False},
        roots=set(),
        workflows=set(),
    )
    content = next(c for p, c in outputs.items() if p.name == "SKILL.md")
    assert content.startswith("---\n")  # front matter preserved at byte 0
    front_matter = content.split("\n---\n", 1)[0]
    # The provenance is a nested `metadata` block, not a top-level key.
    assert "\nmetadata:\n" in front_matter
    assert "  source: library/skills/go/go-qa/SKILL.md" in front_matter
    assert "generated_by:" not in content.splitlines()[1:4]  # not a top-level key
    assert "<!--" not in content  # no HTML comment


def test_generated_skill_metadata_follows_description(tmp_path):
    source = _skill_source(tmp_path)
    renderer = _renderer_with(tmp_path, skills=[source])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False},
        roots=set(),
        workflows=set(),
    )
    content = next(c for p, c in outputs.items() if p.name == "SKILL.md")
    lines = content.splitlines()
    assert lines[1].startswith("name:")
    assert lines[2].startswith("description:")
    assert lines[3] == "metadata:"


def test_generated_prompt_is_left_untouched(tmp_path):
    prompt_file = tmp_path / "library" / "prompts" / "coder" / "plan-story.md"
    prompt_file.parent.mkdir(parents=True)
    original = "# Plan a story\n\nDo the planning.\n"
    prompt_file.write_text(original, encoding="utf-8")
    source = Source(
        kind="prompt", path=prompt_file, rel="coder/plan-story.md", id="coder/plan-story"
    )
    renderer = _renderer_with(tmp_path, prompts=[source])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False},
        roots=set(),
        workflows=set(),
    )
    content = next(c for p, c in outputs.items() if p.name.endswith(".md"))
    # Commands/prompts get nothing added: no metadata, no comment, no banner.
    assert content.strip() == original.strip()
    assert "generated_by" not in content
    assert "<!--" not in content


def test_generated_copilot_prompt_with_front_matter_untouched(tmp_path):
    prompt_file = tmp_path / "library" / "prompts" / "qa" / "plan-qa.prompt.md"
    prompt_file.parent.mkdir(parents=True)
    prompt_file.write_text(
        "---\nname: plan-qa\ndescription: Plan QA\n---\n\n## Steps\n", encoding="utf-8"
    )
    source = Source(
        kind="prompt", path=prompt_file, rel="qa/plan-qa.prompt.md", id="qa/plan-qa"
    )
    renderer = _renderer_with(tmp_path, prompts=[source])
    outputs = renderer.render(
        agents={"claude": False, "codex": False, "copilot": True},
        roots=set(),
        workflows=set(),
    )
    content = next(c for p, c in outputs.items() if p.name.endswith(".prompt.md"))
    assert "generated_by" not in content
    assert "metadata:" not in content
    assert "<!--" not in content
