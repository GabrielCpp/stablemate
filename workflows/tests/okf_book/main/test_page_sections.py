"""A page too large for one writer splits into its head and its `###` nodes, and each problem on it falls in one."""
from __future__ import annotations

from workhorse_workflows.okf_book.main.nodes.page_sections import HEAD, Section, page_sections

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
    parts = page_sections(TEXT)

    assert [section.id for section in parts.sections] == [HEAD, "list-rows", "drop-row"]
    assert parts.by_id("list-rows") == Section("list-rows", tuple(range(9, 17)))
    assert parts.section_text(parts.sections[2]) == "### drop-row\n\n- does: drops a row\n\n"
    assert "A closing note.\n" in parts.section_text(parts.sections[0])


def test_a_problem_falls_in_the_node_it_names_else_the_line_it_names_else_the_head() -> None:
    parts = page_sections(TEXT)

    assert parts.section_id_of_problem(PAGE, f"each of 2 claims on {PAGE}#drop-row does not compile") == "drop-row"
    assert parts.section_id_of_problem(PAGE, f"{PAGE}:11: step-no-verify: a claim has no verify") == "list-rows"
    assert parts.section_id_of_problem(PAGE, f"{PAGE}:27: note-stale: the note is stale") == HEAD
    assert parts.section_id_of_problem(PAGE, "the entries page links no flow") == HEAD
