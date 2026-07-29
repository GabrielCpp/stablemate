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


# --------------------------------------------------------------------------- #
# Section.body / Section.is_empty                                             #
# --------------------------------------------------------------------------- #
#
# "Is this section written?" is the question the whole authored/unwritten contract rests on,
# and before these properties existed every caller answered it by re-splitting the rendered
# text — which is how a scaffold made of nothing but headings came to read as filled.

EMPTY_DOC = """# Story: Foo

## Heading only

## Whitespace only

\x20\x20

## Nested empty

### Background

## Nested written

### Background

Some prose under the sub-heading.

## Written

- a criterion
"""


def test_body_excludes_the_heading_line():
    doc = markdown.split(EMPTY_DOC)
    written = doc.find_section("Written")
    assert "## Written" not in written.body
    assert written.body.strip() == "- a criterion"
    # `text` still carries the heading — the two are different questions, both wanted.
    assert written.text.startswith("## Written")


def test_preamble_body_is_its_whole_text():
    # A level-0 preamble has no heading line to strip, so body == text.
    doc = markdown.split("Intro line.\n\n# Title\n")
    preamble = doc.sections[0]
    assert preamble.level == 0
    assert preamble.body == preamble.text


def test_is_empty_for_a_heading_with_nothing_under_it():
    doc = markdown.split(EMPTY_DOC)
    assert doc.find_section("Heading only").is_empty


def test_is_empty_ignores_whitespace():
    doc = markdown.split(EMPTY_DOC)
    assert doc.find_section("Whitespace only").is_empty


def test_is_empty_when_the_only_content_is_an_empty_sub_heading():
    # `## Context` containing just `### Background` is still unwritten: a heading is a promise
    # of content, not content. Counting it would let a deeper scaffold pass as authored.
    doc = markdown.split(EMPTY_DOC)
    assert doc.find_section("Nested empty").is_empty


def test_is_not_empty_when_a_sub_section_carries_prose():
    doc = markdown.split(EMPTY_DOC)
    assert not doc.find_section("Nested written").is_empty


def test_is_not_empty_with_bullets():
    doc = markdown.split(EMPTY_DOC)
    assert not doc.find_section("Written").is_empty


def test_is_empty_for_the_last_section_of_a_document():
    # The final section's span runs to the end of the body; an off-by-one there would read
    # the document's trailing newline as content (or miss real content on the last line).
    doc = markdown.split("# T\n\n## Last\n")
    assert doc.find_section("Last").is_empty
    doc = markdown.split("# T\n\n## Last\n\nwords\n")
    assert not doc.find_section("Last").is_empty
