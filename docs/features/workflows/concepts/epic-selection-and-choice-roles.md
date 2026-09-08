---
type: concept
slug: epic-selection-and-choice-roles
title: Epic selection and choice roles
---
# Epic selection and choice roles

`_pick_epic` has one responsibility: it opens the repository's Ostler graph, chooses the first
pending epic from the applicable worklist, and constructs an `EpicChoice`. Its successful return
sets `has_epic`, the resolved numbered epic name, the repository-relative directory, the reason,
and worklist progress together. Its empty, completed, and read-failure paths return a choice that
explains why no epic was selected.

[Author main epic selection](author-main-epic-selection.md) is the reference for that selection
algorithm, including the queue source and completion predicate. [Epic choice field
roles](epic-choice-field-roles.md) is the reference for interpreting the `EpicChoice` fields that
the algorithm returns. Neither replaces the other: the implementation in
`workflows/src/workhorse_workflows/author/main/nodes/epics.py::_pick_epic` requires both the
selection behaviour and its result contract to understand the outcome.

- code: `workflows/src/workhorse_workflows/author/main/nodes/epics.py::_pick_epic`
- rule: use Author main epic selection to determine how an epic is chosen, and Epic choice field roles to interpret the resulting `EpicChoice`; neither concept is a replacement for the other
- detail: [Epic selection documentation roles](epic-selection-documentation-roles.md)
