from __future__ import annotations

from pathlib import Path

from ostler import markdown, trace
from ostler.model import load


def test_markdown_roundtrip_identity():
    text = "---\nsurface: a/b\nroute: /a/b\n---\n# Title\n\nbody\n"
    doc = markdown.split(text)
    assert doc.has_frontmatter
    assert doc.frontmatter["surface"] == "a/b"
    assert doc.render() == text  # exact round-trip, no churn


def test_markdown_no_frontmatter():
    text = "# Just a heading\n\nbody only\n"
    doc = markdown.split(text)
    assert not doc.has_frontmatter
    assert doc.render() == text


def test_exploration_profile_when_no_epics(tmp_path: Path):
    (tmp_path / "docs/knowledge/area").mkdir(parents=True)
    (tmp_path / "docs/knowledge/area/note.md").write_text(
        "---\nsurface: area/note\n---\nhi\n", encoding="utf-8")
    graph = load(tmp_path)
    assert graph.profile == "exploration"
    assert graph.org_name == tmp_path.name
    assert len(graph.knowledge) == 1


def test_org_name_override_from_config(tmp_path: Path):
    (tmp_path / "docs/knowledge").mkdir(parents=True)
    (tmp_path / "ostler.yml").write_text(
        "organization:\n  name: custom-org\n", encoding="utf-8")
    graph = load(tmp_path)
    assert graph.org_name == "custom-org"


def test_trace_story_and_seed(repo: Path):
    graph = load(repo)
    lines, found = trace.run(graph, "01-foo")
    assert found and any("seed-a1" in ln for ln in lines)

    lines, found = trace.run(graph, "seed-a1")
    assert found and any("covered by story" in ln and "01-foo" in ln for ln in lines)

    lines, found = trace.run(graph, "area/rec")
    assert found and any("surface" in ln for ln in lines)

    lines, found = trace.run(graph, "does-not-exist")
    assert not found
