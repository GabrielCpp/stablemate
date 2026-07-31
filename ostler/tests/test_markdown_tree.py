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


# --- parser-backed behaviour the old regex/line-scan implementation got wrong -------------


def test_links_inside_code_are_not_links():
    """A link in a fenced block or an inline span is not a `link_open` token.

    The blanking hack this replaces could not tell `strategies[idx](x)` in a snippet from
    a link, so a snippet's punctuation showed up as a broken reference.
    """
    doc = markdown.split(
        "Real [a](/a.md).\n\n```python\nx = strategies[idx](y)\nsee [b](/b.md)\n```\n\n"
        "Inline `[c](/c.md)` too.\n"
    )
    assert doc.refs.links == [("a", "/a.md")]


def test_link_line_is_the_link_s_own_line_not_the_block_s():
    """A link on the third line of a wrapped paragraph reports line 3, not the block start."""
    text = "A paragraph that\nwraps and has [d](/d.md)\non the next line.\n"
    assert list(markdown.iter_links(text)) == [("d", "/d.md", 2)]


def test_a_code_span_that_wraps_does_not_shift_the_links_after_it():
    """Found by diffing 332 links over a real book: every link after a wrapped span read early.

    CommonMark turns a line ending *inside* a code span into a space, so the whole span comes
    back as one `code_inline` token with no newline in it. Counting newlines across the
    children therefore under-counts, and the fix is to ask the parser where the link began
    rather than to re-derive it.
    """
    text = "Carries `datasheet.id REFERENCES ressource(id) ON\nDELETE CASCADE` and then\n[e](/e.md).\n"
    assert list(markdown.iter_links(text)) == [("e", "/e.md", 3)]


def test_a_link_label_that_wraps_reads_as_one_link():
    """The old blank-out-the-code-first pass lost the label and mis-placed what followed."""
    text = "- run: `make x` and [`app/console cache:clear\n  --env=prod`](/console.md) after.\n"
    assert list(markdown.iter_links(text)) == [
        ("app/console cache:clear --env=prod", "/console.md", 1),
    ]


def test_frontmatter_survives_crlf():
    """The line scan returned *no frontmatter at all* for a CRLF file — a silent total loss."""
    doc = markdown.split("---\r\ntitle: t\r\n---\r\n\r\nbody\r\n")
    assert doc.frontmatter == {"title": "t"}
    assert doc.body == "\nbody\n"


def test_frontmatter_survives_a_missing_trailing_newline():
    doc = markdown.split("---\ntitle: t\n---")
    assert doc.frontmatter == {"title": "t"}
    assert doc.body == ""


def test_frontmatter_survives_a_trailing_space_on_the_closing_fence():
    doc = markdown.split("---\ntitle: t\n--- \n\nbody\n")
    assert doc.frontmatter == {"title": "t"}


def test_a_rule_inside_a_block_scalar_does_not_close_the_frontmatter():
    """A `---` indented into a block scalar is content, not a fence.

    The line scan `.strip()`ped every line before comparing, so it closed here and handed
    back `{"title": "t", "note": "---"}` with the rest of the frontmatter as *body*. (A
    `---` indented by one to three spaces genuinely *is* a thematic break in CommonMark,
    and closing there is correct — this pins the case where it is not.)
    """
    doc = markdown.split("---\ntitle: t\nnote: |\n    ---\nmore: m\n---\n\nbody\n")
    assert doc.frontmatter == {"title": "t", "note": "---\n", "more": "m"}
    assert doc.body == "\nbody\n"


def test_a_bare_rule_is_not_frontmatter():
    """`---` with nothing to close it is a horizontal rule, and the parser says so."""
    assert markdown.split("---\n\ntext\n").frontmatter is None
    assert markdown.split("---").frontmatter is None


TABLE_DOC = """# Placeholders

| Placeholder | Stands for |
| ----------- | ---------- |
| `acme`      | a client repo |
| `web-app`   | a repo in a workspace |

- a real bullet
"""


def test_tables_are_parsed_not_paragraphs():
    section = markdown.split(TABLE_DOC).find_section("Placeholders")
    table = section.tables[0]
    assert table.headers == ["Placeholder", "Stands for"]
    assert table.rows == [
        ["`acme`", "a client repo"],
        ["`web-app`", "a repo in a workspace"],
    ]
    assert (table.line_start, table.line_end) == (2, 6)


def test_table_rows_are_not_mistaken_for_bullets():
    section = markdown.split(TABLE_DOC).find_section("Placeholders")
    assert [b.text for b in section.bullets] == ["a real bullet"]


def test_table_records_and_column_lookup():
    table = markdown.split(TABLE_DOC).find_section("Placeholders").tables[0]
    assert table.records[0] == {"Placeholder": "`acme`", "Stands for": "a client repo"}
    assert table.column("placeholder") == ["`acme`", "`web-app`"]
    assert table.column("nope") == []
