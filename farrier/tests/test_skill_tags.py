"""A skill's `tags:` are what a workflow prompt can ask for without naming it."""
from __future__ import annotations

from pathlib import Path

from farrier.frontmatter import frontmatter_tags, normalize_tags
from farrier.install import Renderer, Source


def _skill(tmp_path: Path, name: str, front: str = "", body: str = "Rules.\n") -> Source:
    """A library skill whose front matter is exactly *front* (`tags:` lines and all)."""
    skill_file = tmp_path / "library" / "skills" / "stack" / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(
        f"---\nname: {name}\ndescription: A {name} skill\n{front}---\n\n# {name}\n\n{body}",
        encoding="utf-8",
    )
    return Source(
        kind="skill",
        path=skill_file,
        rel=f"stack/{name}/SKILL.md",
        id=f"stack/{name}",
    )


def _renderer(tmp_path: Path, skills: list[Source]) -> Renderer:
    return Renderer(
        repo=tmp_path,
        prefix="demo",
        repo_config={},
        template_values={},
        skills=skills,
        prompts=[],
    )


def test_normalize_tags_lowercases_dedupes_and_keeps_order():
    assert normalize_tags(["Web", " TESTS ", "web"]) == ["web", "tests"]


def test_normalize_tags_splits_the_string_form():
    assert normalize_tags("web, tests") == ["web", "tests"]


def test_normalize_tags_of_a_non_list_is_no_tags():
    assert normalize_tags(None) == []
    assert normalize_tags(42) == []


def test_frontmatter_tags_reads_the_flow_list(tmp_path):
    source = _skill(tmp_path, "web-tests", front="tags: [Web, tests]\n")
    assert frontmatter_tags(source.path.read_text(encoding="utf-8")) == ["web", "tests"]


def test_frontmatter_tags_reads_the_block_list(tmp_path):
    source = _skill(tmp_path, "web-std", front="tags:\n  - web\n  - standards\n")
    assert frontmatter_tags(source.path.read_text(encoding="utf-8")) == [
        "web",
        "standards",
    ]


def test_frontmatter_tags_of_an_untagged_or_broken_file_is_empty(tmp_path):
    plain = _skill(tmp_path, "plain")
    assert frontmatter_tags(plain.path.read_text(encoding="utf-8")) == []
    assert frontmatter_tags("no front matter here\n") == []
    assert frontmatter_tags("---\ntags: [web\n---\n\nbody\n") == []


def test_generated_skill_carries_its_tags_in_the_metadata_block(tmp_path):
    renderer = _renderer(tmp_path, [_skill(tmp_path, "web-tests", "tags: [web, tests]\n")])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False}, roots=set()
    )
    content = next(c for p, c in outputs.items() if p.name == "SKILL.md")
    front_matter = content.split("\n---\n", 1)[0]
    assert "\nmetadata:\n" in front_matter
    assert "  tags: [web, tests]\n" in front_matter + "\n"


def test_generated_skill_omits_tags_when_the_source_declares_none(tmp_path):
    renderer = _renderer(tmp_path, [_skill(tmp_path, "plain")])
    outputs = renderer.render(
        agents={"claude": True, "codex": False, "copilot": False}, roots=set()
    )
    content = next(c for p, c in outputs.items() if p.name == "SKILL.md")
    assert "tags:" not in content.split("\n---\n", 1)[0]


def test_context_manifest_publishes_tags_for_every_alias(tmp_path):
    renderer = _renderer(tmp_path, [_skill(tmp_path, "web-tests", "tags: [web, tests]\n")])
    manifest = renderer.context_manifest("claude")
    tags = manifest["instruction_tags"]
    assert set(tags) == {k for k, _ in renderer.skill_lookup.items()}
    assert all(value == ["web", "tests"] for value in tags.values())
    assert set(tags) <= set(manifest["instructions"])


def test_context_manifest_omits_the_untagged(tmp_path):
    renderer = _renderer(tmp_path, [_skill(tmp_path, "plain")])
    assert renderer.context_manifest("claude")["instruction_tags"] == {}


def test_skills_with_tags_is_an_and(tmp_path):
    web_tests = _skill(tmp_path, "web-tests", "tags: [web, tests]\n")
    web_std = _skill(tmp_path, "web-std", "tags: [web, standards]\n")
    renderer = _renderer(tmp_path, [web_tests, web_std])
    assert renderer.skills_with_tags(["web"]) == [web_tests, web_std]
    assert renderer.skills_with_tags(["web", "tests"]) == [web_tests]
    assert renderer.skills_with_tags(["web", "mobile"]) == []
    assert renderer.skills_with_tags([]) == []


def test_find_by_tags_renders_the_matches_as_a_reference_list(tmp_path):
    renderer = _renderer(
        tmp_path,
        [
            _skill(tmp_path, "web-tests", "tags: [web, tests]\n"),
            _skill(tmp_path, "web-std", "tags: [web, standards]\n"),
        ],
    )
    rendered = renderer.render_templates(
        '{{ find_by_tags("web") }}', "claude", tmp_path / "AGENTS.md"
    )
    assert rendered == (
        "`.claude/skills/demo-stack-web-std/SKILL.md`, "
        "`.claude/skills/demo-stack-web-tests/SKILL.md`"
    )


def test_find_by_tags_renders_nothing_when_the_repo_has_no_match(tmp_path):
    renderer = _renderer(tmp_path, [_skill(tmp_path, "web-tests", "tags: [web, tests]\n")])
    rendered = renderer.render_templates(
        '{{ find_by_tags("mobile") | default("(none installed)", true) }}',
        "claude",
        tmp_path / "AGENTS.md",
    )
    assert rendered == "(none installed)"
