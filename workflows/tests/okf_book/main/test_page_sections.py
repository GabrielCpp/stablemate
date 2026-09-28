"""A page too large for one writer splits into its head and its `###` nodes, and each problem on it falls in one."""
from __future__ import annotations

from workhorse_workflows.okf_book.main.nodes.page_sections import HEAD_SECTION_ID, Section, page_sections
from workhorse_workflows.okf_book.shared.page_check import PageProblem

PAGE = "docs/features/ledger/http/ledger-api.md"
TEXT = """---
type: server
---

# Ledger API

## Endpoints

### list-rows

- does: lists the rows

```
### not-a-node
```

### drop-row

- does: drops a row

## Notes

A closing note.
"""


def test_a_page_splits_at_each_node_and_every_other_line_is_its_head() -> None:
    sections_of_page = page_sections(TEXT)

    assert [section.id for section in sections_of_page.sections] == [HEAD_SECTION_ID, "list-rows", "drop-row"]
    assert sections_of_page.by_id("list-rows") == Section("list-rows", tuple(range(9, 17)))
    assert sections_of_page.section_text(sections_of_page.sections[2]) == "### drop-row\n\n- does: drops a row\n\n"
    assert "A closing note.\n" in sections_of_page.section_text(sections_of_page.sections[0])


def test_a_problem_falls_in_the_node_it_names_else_the_line_it_names_else_the_head() -> None:
    sections_of_page = page_sections(TEXT)

    assert sections_of_page.section_id_of_problem(PageProblem(PAGE, "2 claims do not compile", node=f"{PAGE}#drop-row")) == "drop-row"
    assert sections_of_page.section_id_of_problem(PageProblem(PAGE, "a claim has no verify", line=11)) == "list-rows"
    assert sections_of_page.section_id_of_problem(PageProblem(PAGE, "the note is stale", line=27)) == HEAD_SECTION_ID
    assert sections_of_page.section_id_of_problem(PageProblem(PAGE, "a node no section holds", node=f"{PAGE}#gone", line=11)) == "list-rows"
    assert sections_of_page.section_id_of_problem(PageProblem(PAGE, "the entries page links no flow")) == HEAD_SECTION_ID
