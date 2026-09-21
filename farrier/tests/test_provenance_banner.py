"""Generated skills are stamped with their library source in the `metadata` field."""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from farrier.frontmatter import frontmatter_mapping, split_front_matter
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
    assert library_source_path(source) == "library/skills/go/go-qa/SKILL.md"


def test_metadata_block_names_source_and_warns(tmp_path):
    block = skill_metadata_block(
        _skill_source(tmp_path), ".claude/skills/demo-go-qa/SKILL.md"
    )
    assert block.startswith("metadata:\n")
    assert "  generated_by: farrier\n" in block
    assert "  source: library/skills/go/go-qa/SKILL.md\n" in block
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
    )
    content = next(c for p, c in outputs.items() if p.name == "SKILL.md")
    assert content.startswith("---\n")
    front_matter = content.split("\n---\n", 1)[0]
    assert "\nmetadata:\n" in front_matter
    assert "  source: library/skills/go/go-qa/SKILL.md" in front_matter
    assert (
        '  resolve: "farrier source .claude/skills/demo-go-qa/SKILL.md"'
        in front_matter
    )
    assert "generated_by:" not in content.splitlines()[1:4]
    assert "<!--" not in content


def test_generated_skill_metadata_follows_description(tmp_path):
    source = _skill_source(tmp_path)
    renderer = _renderer_with(tmp_path, skills=[source])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False},
        roots=set(),
    )
    content = next(c for p, c in outputs.items() if p.name == "SKILL.md")
    lines = content.splitlines()
    assert lines[1].startswith("name:")
    assert lines[2].startswith("description:")
    assert lines[3] == "metadata:"


def _prompt_source(tmp_path: Path, body: str, rel: str = "stablemate/plan-story.md") -> Source:
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
    )
    return next(c for p, c in outputs.items() if p.name.endswith(".md"))


@pytest.mark.parametrize("with_header", [False, True])
@pytest.mark.parametrize("target,directory,suffix", [
    ("claude", ".claude/commands", ".md"),
    ("codex", ".agents/prompts", ".prompt.md"),
    ("copilot", ".github/prompts", ".prompt.md"),
])
def test_prompt_carries_description_and_provenance(
    tmp_path: Path, with_header: bool, target: str, directory: str, suffix: str
) -> None:
    body = "# Plan a story\n\nDo the planning.\n"
    header = (
        "---\ndescription: Plan a coding story\nargument-hint: <story>\n"
        "tags: [planning]\n---\n\n"
        if with_header else ""
    )
    source = _prompt_source(tmp_path, header + body)
    outputs = _renderer_with(tmp_path, prompts=[source]).render(
        agents={target: True}, roots=set()
    )
    dest = f"{directory}/demo-stablemate-plan-story{suffix}"
    content = outputs[tmp_path / dest]
    metadata = frontmatter_mapping(content)
    assert metadata.get("description") == (
        "Plan a coding story" if with_header else "Plan a story"
    )
    provenance = metadata["metadata"]
    assert provenance["generated_by"] == "farrier"
    assert provenance["source"] == "library/prompts/stablemate/plan-story.md"
    assert provenance["resolve"] == f"farrier source {dest}"
    assert "make agent-install" in provenance["do_not_edit"]
    if with_header:
        assert metadata["argument-hint"] == "<story>"
        assert provenance["tags"] == ["planning"]
    assert split_front_matter(content)[1] == body


def test_generated_command_gets_description_front_matter(tmp_path):
    source = _prompt_source(tmp_path, "# Plan a story\n\nDo the planning.\n")
    content = _render_claude_command(tmp_path, source)
    assert content.startswith("---\n")
    front_matter = content.split("\n---\n", 1)[0]
    assert 'description: "Plan a story"' in front_matter
    assert "\nmetadata:\n" in front_matter
    assert "  generated_by: farrier\n" in front_matter
    assert "  source: library/prompts/stablemate/plan-story.md\n" in front_matter
    assert "  do_not_edit:" in front_matter
    assert "<!--" not in content
    assert content.rstrip().endswith("Do the planning.")


def test_generated_command_prefers_source_description_and_drops_internal_keys(tmp_path):
    source = _prompt_source(
        tmp_path,
        "---\nagent: agent\nname: plan-story\ndescription: Plan a coding story\n---\n\n# Heading\n\nBody.\n",
    )
    content = _render_claude_command(tmp_path, source)
    front_matter = content.split("\n---\n", 1)[0]
    assert 'description: "Plan a coding story"' in front_matter
    assert "agent:" not in front_matter
    assert "name:" not in front_matter


def test_generated_command_passes_through_argument_hint(tmp_path):
    source = _prompt_source(
        tmp_path,
        "---\ndescription: Check a PR\nargument-hint: <pr-number>\n---\n\n# Check\n\nBody.\n",
    )
    content = _render_claude_command(tmp_path, source)
    assert 'argument-hint: "<pr-number>"' in content.split("\n---\n", 1)[0]


def test_generated_command_carries_tags_into_metadata(tmp_path):
    source = _prompt_source(
        tmp_path,
        "---\ndescription: Check a PR\ntags: [grill]\n---\n\n# Check\n\nBody.\n",
    )
    content = _render_claude_command(tmp_path, source)
    front_matter = content.split("\n---\n", 1)[0]
    assert "  tags: [grill]" in front_matter


def _overlay_skill(tmp_path: Path, name: str, body: str) -> Source:
    skill_file = tmp_path / "library" / "skills" / "go" / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(f"---\nname: {name}\n---\n\n{body}", encoding="utf-8")
    return Source(
        kind="skill", path=skill_file, rel=f"go/{name}/SKILL.md", id=f"go/{name}"
    )


def test_claude_pointer_gets_the_html_comment_banner(tmp_path):
    source = _overlay_skill(tmp_path, "go-qa", "# Go QA\nRules.\n")
    renderer = _renderer_with(tmp_path, skills=[source])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    content = renderer.render_claude_pointer(["demo-go-qa"], target_dir / "CLAUDE.md")
    assert content.startswith("<!--\n")
    banner = content.split("-->", 1)[0]
    assert "generated by farrier" in banner
    assert "library/skills/go/go-qa/SKILL.md" in banner
    assert "make agent-install" in banner
    assert "localInstructions" in banner
    assert "`farrier source svc/CLAUDE.md`" in banner
    assert "@AGENTS.md" in content.split("-->", 1)[1]
    assert "# Go QA" not in content


def test_claude_pointer_banner_lists_all_aggregated_sources(tmp_path):
    a = _overlay_skill(tmp_path, "go-qa", "# A\n")
    b = _overlay_skill(tmp_path, "go-arch", "# B\n")
    renderer = _renderer_with(tmp_path, skills=[a, b])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    content = renderer.render_claude_pointer(
        ["demo-go-qa", "demo-go-arch"], target_dir / "CLAUDE.md"
    )
    banner = content.split("-->", 1)[0]
    assert "library/skills/go/go-qa/SKILL.md" in banner
    assert "library/skills/go/go-arch/SKILL.md" in banner


def test_aggregated_agents_file_carries_no_banner_at_all(tmp_path):
    source = _overlay_skill(tmp_path, "go-qa", "# Go QA\nRules.\n")
    renderer = _renderer_with(tmp_path, skills=[source])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    content = renderer.render_local_instruction(
        ["demo-go-qa"], "codex", target_dir / "AGENTS.md", False
    )
    assert "<!--" not in content
    assert "do not edit" not in content.lower()
    assert content.startswith("# Go QA")


def test_claude_pointer_imports_the_readme_alongside_the_body(tmp_path):
    source = _overlay_skill(tmp_path, "go-qa", "# Go QA\n")
    renderer = _renderer_with(tmp_path, skills=[source])
    target_dir = tmp_path / "svc"
    target_dir.mkdir()
    (target_dir / "README.md").write_text("Local readme.\n", encoding="utf-8")
    content = renderer.render_claude_pointer(
        ["demo-go-qa"], target_dir / "CLAUDE.md", readme_import=True
    )
    assert content.startswith("<!--\n")
    assert "@AGENTS.md" in content
    assert "@README.md" in content


def test_generated_copilot_prompt_preserves_native_header_fields(tmp_path):
    prompt_file = tmp_path / "library" / "prompts" / "qa" / "plan-qa.prompt.md"
    prompt_file.parent.mkdir(parents=True)
    prompt_file.write_text(
        "---\nname: plan-qa\ndescription: Plan QA\nagent: agent\n"
        "tools: [search, read]\nmodel: [model-a, model-b]\n---\n\n## Steps\n",
        encoding="utf-8"
    )
    source = Source(
        kind="prompt", path=prompt_file, rel="qa/plan-qa.prompt.md", id="qa/plan-qa"
    )
    renderer = _renderer_with(tmp_path, prompts=[source])
    outputs = renderer.render(
        agents={"claude": False, "codex": False, "copilot": True},
        roots=set(),
    )
    content = next(c for p, c in outputs.items() if p.name.endswith(".prompt.md"))
    header = frontmatter_mapping(content)
    assert header["name"] == "plan-qa"
    assert header["agent"] == "agent"
    assert header["tools"] == ["search", "read"]
    assert header["model"] == ["model-a", "model-b"]
    assert header["metadata"]["generated_by"] == "farrier"
    assert "<!--" not in content
