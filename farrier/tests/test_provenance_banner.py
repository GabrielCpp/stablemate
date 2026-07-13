"""Generated skills are stamped with their library source in the `metadata` field.

A generated skill is a *copy* of a library SKILL.md. Without a marker an agent edits
the copy and loses the change on the next `make agent-install`. So each generated
SKILL.md names its source of truth in the openskill `metadata` field
(openskill.sh/docs/creators/skill-format).

Prompts are not skills, so they carry no openskill `metadata` block. But a generated
Claude command still needs a `description` in its front matter — without one,
claude-code-acp advertises nothing over ACP and the command never appears in Zed's
autocomplete. So the claude target emits a header (description / argument-hint /
model / allowed-tools) plus the same `metadata:` provenance block skills get, while
codex/copilot prompts are left untouched.

Aggregated instruction files (localInstructions → CLAUDE.md) cannot carry front
matter — Claude injects them verbatim. There the provenance is a block-level HTML
comment: Claude strips those before injection, so it is visible to humans only.
Only the claude target gets the comment; other agents do not strip HTML comments.

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
    block = skill_metadata_block(
        _skill_source(tmp_path), ".claude/skills/demo-go-qa/SKILL.md"
    )
    assert block.startswith("metadata:\n")
    assert "  generated_by: farrier\n" in block
    assert "  source: library/skills/go/go-qa/SKILL.md\n" in block
    # The resolve field is a copy-pasteable command back to the editable source; the
    # source path stays library-anchored (portable), no absolute path baked in.
    assert (
        '  resolve: "farrier source .claude/skills/demo-go-qa/SKILL.md"\n' in block
    )
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
    # resolve names the generated file's own repo-relative path (prefix `demo` +
    # skill `go-qa` → .claude/skills/demo-go-qa/SKILL.md).
    assert (
        '  resolve: "farrier source .claude/skills/demo-go-qa/SKILL.md"'
        in front_matter
    )
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


def _prompt_source(tmp_path: Path, body: str, rel: str = "coder/plan-story.md") -> Source:
    prompt_file = tmp_path / "library" / "prompts" / Path(rel)
    prompt_file.parent.mkdir(parents=True, exist_ok=True)
    prompt_file.write_text(body, encoding="utf-8")
    return Source(
        kind="prompt", path=prompt_file, rel=rel, id=rel.removesuffix(".md")
    )


def _render_claude_command(tmp_path: Path, source: Source) -> str:
    renderer = _renderer_with(tmp_path, prompts=[source])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False},
        roots=set(),
        workflows=set(),
    )
    return next(c for p, c in outputs.items() if p.name.endswith(".md"))


def test_generated_command_gets_description_front_matter(tmp_path):
    source = _prompt_source(tmp_path, "# Plan a story\n\nDo the planning.\n")
    content = _render_claude_command(tmp_path, source)
    # A header is required so claude-code-acp advertises the command to Zed.
    assert content.startswith("---\n")
    front_matter = content.split("\n---\n", 1)[0]
    # No explicit description → falls back to the body's first heading.
    assert 'description: "Plan a story"' in front_matter
    # Provenance is the same structured metadata block skills get (not a comment).
    assert "\nmetadata:\n" in front_matter
    assert "  generated_by: farrier\n" in front_matter
    assert "  source: library/prompts/coder/plan-story.md\n" in front_matter
    assert "  do_not_edit:" in front_matter
    assert "<!--" not in content
    # The body survives below the header.
    assert content.rstrip().endswith("Do the planning.")


def test_generated_command_prefers_source_description_and_drops_internal_keys(tmp_path):
    source = _prompt_source(
        tmp_path,
        "---\nagent: agent\nname: plan-story\ndescription: Plan a coding story\n---\n\n# Heading\n\nBody.\n",
    )
    content = _render_claude_command(tmp_path, source)
    front_matter = content.split("\n---\n", 1)[0]
    assert 'description: "Plan a coding story"' in front_matter
    # Farrier-internal selection keys never leak into the command header.
    assert "agent:" not in front_matter
    assert "name:" not in front_matter


def test_generated_command_passes_through_argument_hint(tmp_path):
    source = _prompt_source(
        tmp_path,
        "---\ndescription: Check a PR\nargument-hint: <pr-number>\n---\n\n# Check\n\nBody.\n",
    )
    content = _render_claude_command(tmp_path, source)
    assert 'argument-hint: "<pr-number>"' in content.split("\n---\n", 1)[0]


def _overlay_skill(tmp_path: Path, name: str, body: str) -> Source:
    skill_file = tmp_path / "library" / "skills" / "go" / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(f"---\nname: {name}\n---\n\n{body}", encoding="utf-8")
    return Source(
        kind="skill", path=skill_file, rel=f"go/{name}/SKILL.md", id=f"go/{name}"
    )


def test_local_instruction_claude_gets_html_comment_banner(tmp_path):
    source = _overlay_skill(tmp_path, "go-qa", "# Go QA\nRules.\n")
    renderer = _renderer_with(tmp_path, skills=[source])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    content = renderer.render_local_instruction(
        ["demo-go-qa"], "claude", target_dir / "CLAUDE.md", "none"
    )
    # Banner is a block-level HTML comment at byte 0 — Claude strips it before
    # injection, so it never reaches the agent; humans see the regen recipe.
    assert content.startswith("<!--\n")
    banner = content.split("-->", 1)[0]
    assert "generated by farrier" in banner
    assert "library/skills/go/go-qa/SKILL.md" in banner
    assert "make agent-install" in banner
    assert "localInstructions" in banner
    # Copy-pasteable resolve command, repo-root-relative — same contract as the
    # `resolve:` field in skill front matter.
    assert "`farrier source svc/CLAUDE.md`" in banner
    # Skill body survives below the banner, outside the comment.
    assert "# Go QA" in content.split("-->", 1)[1]


def test_local_instruction_banner_lists_all_aggregated_sources(tmp_path):
    a = _overlay_skill(tmp_path, "go-qa", "# A\n")
    b = _overlay_skill(tmp_path, "go-arch", "# B\n")
    renderer = _renderer_with(tmp_path, skills=[a, b])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    content = renderer.render_local_instruction(
        ["demo-go-qa", "demo-go-arch"], "claude", target_dir / "CLAUDE.md", "none"
    )
    banner = content.split("-->", 1)[0]
    assert "library/skills/go/go-qa/SKILL.md" in banner
    assert "library/skills/go/go-arch/SKILL.md" in banner


def test_local_instruction_codex_stays_comment_free(tmp_path):
    # Codex does not strip HTML comments, so the banner would leak into the
    # agent's context — AGENTS.md/CODEX.md stay untouched.
    source = _overlay_skill(tmp_path, "go-qa", "# Go QA\nRules.\n")
    renderer = _renderer_with(tmp_path, skills=[source])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    content = renderer.render_local_instruction(
        ["demo-go-qa"], "codex", target_dir / "AGENTS.md", "none"
    )
    assert "<!--" not in content


def test_local_instruction_banner_precedes_readme_import(tmp_path):
    source = _overlay_skill(tmp_path, "go-qa", "# Go QA\n")
    renderer = _renderer_with(tmp_path, skills=[source])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("Local readme.\n", encoding="utf-8")
    content = renderer.render_local_instruction(
        ["demo-go-qa"], "claude", target_dir / "CLAUDE.md", "import"
    )
    assert content.startswith("<!--\n")
    assert "@README.md" in content


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
