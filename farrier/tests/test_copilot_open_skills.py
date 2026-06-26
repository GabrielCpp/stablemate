"""Tests that copilot now uses the open skills format (.github/skills/{name}/SKILL.md)
instead of the legacy flat-file format (.github/instructions/{name}.instructions.md).
"""
from __future__ import annotations

import textwrap
from pathlib import Path


from farrier.install import Renderer, Source


def _make_renderer(tmp_path: Path, skill_content: str = "") -> tuple[Renderer, Source]:
    """Build a minimal Renderer with one skill source."""
    skill_dir = tmp_path / "library" / "skills" / "demo"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "go" / "SKILL.md"
    skill_file.parent.mkdir()
    skill_file.write_text(
        textwrap.dedent(skill_content or "# Go\nUse for Go work.\n"),
        encoding="utf-8",
    )
    source = Source(kind="skill", path=skill_file, rel="demo/go/SKILL.md", id="demo/go")
    renderer = Renderer(
        repo=tmp_path,
        prefix="demo",
        repo_config={},
        template_values={},
        skills=[source],
        prompts=[],
    )
    return renderer, source


def test_skill_dir_path_copilot_returns_github_skills(tmp_path):
    renderer, _ = _make_renderer(tmp_path)
    assert renderer.skill_dir_path("copilot") == tmp_path / ".github" / "skills"


def test_skill_output_path_copilot_uses_open_skills_format(tmp_path):
    renderer, source = _make_renderer(tmp_path)
    path = renderer.skill_output_path(source.id, "copilot")
    assert path == tmp_path / ".github" / "skills" / "demo-go" / "SKILL.md"


def test_skill_output_path_copilot_instruction_still_works(tmp_path):
    """The copilot-instruction target remains available for explicit use."""
    renderer, source = _make_renderer(tmp_path)
    path = renderer.skill_output_path(source.id, "copilot-instruction")
    assert path == tmp_path / ".github" / "instructions" / "demo-go.instructions.md"


def test_context_manifest_copilot_uses_open_skills_paths(tmp_path):
    renderer, _ = _make_renderer(tmp_path)
    manifest = renderer.context_manifest("copilot")
    for path in manifest["instructions"].values():
        assert path.startswith(".github/skills/"), (
            f"Expected .github/skills/ prefix, got: {path}"
        )
        assert path.endswith("/SKILL.md"), f"Expected SKILL.md suffix, got: {path}"
    assert manifest["skill_dir"] == ".github/skills"


def test_context_manifest_copilot_no_instructions_path(tmp_path):
    renderer, _ = _make_renderer(tmp_path)
    manifest = renderer.context_manifest("copilot")
    for path in manifest["instructions"].values():
        assert ".github/instructions" not in path, (
            f"Found legacy instructions path: {path}"
        )


def test_render_copilot_skills_include_frontmatter(tmp_path):
    renderer, _ = _make_renderer(tmp_path, "# Go\nUse for Go work.\n")
    outputs = renderer.render(
        agents={"copilot": True, "claude": False, "codex": False},
        roots=set(),
        workflows=set(),
    )
    skill_path = tmp_path / ".github" / "skills" / "demo-go" / "SKILL.md"
    assert skill_path in outputs, f"Expected {skill_path} in outputs"
    content = outputs[skill_path]
    assert content.startswith("---\n"), "Expected YAML frontmatter"
    assert "name: demo-go" in content
    assert "description:" in content


def test_render_copilot_no_legacy_instructions_files(tmp_path):
    renderer, _ = _make_renderer(tmp_path)
    outputs = renderer.render(
        agents={"copilot": True, "claude": False, "codex": False},
        roots=set(),
        workflows=set(),
    )
    for path in outputs:
        assert ".github/instructions" not in str(path), (
            f"Legacy instructions file written: {path}"
        )
