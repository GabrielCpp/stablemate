from __future__ import annotations

from ostler import markdown

DOC = """---
surface: a/b
---
Intro preamble line.

# Story: Foo

## Implementation Status

- **Status**: Not started

## Acceptance Criteria

- First criterion works. See `docs/knowledge/area/first.md`.
- Second one too.
  - a nested detail in `docs/knowledge/area/nested.md`
- Links to `docs/knowledge/area/rec.json`.

## Evidence

See [old shot](docs/evidence/old.png).
"""


def test_frontmatter_and_roundtrip():
    doc = markdown.split(DOC)
    assert doc.frontmatter["surface"] == "a/b"
    assert doc.render() == DOC  # byte-exact


def test_section_tree_nesting():
    doc = markdown.split(DOC)
    titles = [s.title for s in doc.walk_sections()]
    # preamble (''), the H1, and its three H2 children
    assert "" in titles
    assert "Story: Foo" in titles
    foo = doc.find_section("Story: Foo")
    assert {c.title for c in foo.children} == {
        "Implementation Status", "Acceptance Criteria", "Evidence"}


def test_section_scoped_refs():
    doc = markdown.split(DOC)
    ac = doc.find_section("Acceptance Criteria")
    assert ac.refs.knowledge_paths == ["docs/knowledge/area/first.md",
                                      "docs/knowledge/area/nested.md",
                                      "docs/knowledge/area/rec.json"]
    # the Evidence section's link does not leak into Acceptance Criteria
    ev = doc.find_section("Evidence")
    assert ev.refs.links == [("old shot", "docs/evidence/old.png")]
    assert ac.refs.links == []


def test_bullets_and_nesting():
    doc = markdown.split(DOC)
    ac = doc.find_section("Acceptance Criteria")
    assert len(ac.bullets) == 3
    second = ac.bullets[1]
    assert second.children and "nested detail" in second.children[0].text
    # a bullet exposes its own refs
    assert ac.bullets[0].refs.knowledge_paths == ["docs/knowledge/area/first.md"]
    assert second.children[0].refs.knowledge_paths == ["docs/knowledge/area/nested.md"]


def test_source_spans_map_back_to_body():
    doc = markdown.split(DOC)
    ac = doc.find_section("Acceptance Criteria")
    # the section's raw text slice really is its bytes in the body
    assert ac.text.startswith("## Acceptance Criteria")
    assert "nested detail" in ac.text
