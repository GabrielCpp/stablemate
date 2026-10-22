---
type: format
slug: epic-author-done
title: Epic author completion
---
# Epic author completion

The terminal result marks completion of authoring one explicit epic after document validation. It
returns the validated epic identity, its canonical paths, the researched-seed count, and the number
of rework and PM-answer turns used. A `blocked` result carries the notes that stopped it.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [author epic-author subflow](../concepts/author-epic-author-subflow.md)

## Fields

### status
- type: literal string `authored` or `blocked`
- default: `"authored"`
- required: false
- semantics: terminal status: `authored` when the explicit epic crossed the authoring boundary, `blocked` when a budget ran out
- verify: json_path(path="$.status", equals="authored")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### epic
- type: string
- default: `""`
- required: false
- semantics: validated canonical name of the authored epic
- verify: json_path(path="$.epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### epic_dir
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical directory containing the authored epic
- verify: json_path(path="$.epic_dir", equals="docs/stories/acme-story")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### epic_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical `epic.md` path validated before completion
- verify: json_path(path="$.epic_path", matches="/epic\\.md$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### seed_count
- type: integer
- default: `0`
- required: false
- semantics: number of researched seeds present in the completed epic
- verify: json_path(path="$.seed_count", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### notes
- type: string
- default: `""`
- required: false
- semantics: the validation errors or question that left the epic blocked
- verify: json_path(path="$.notes", equals="")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### reworks
- type: integer
- default: `0`
- required: false
- semantics: number of validation rework passes the writer made
- verify: json_path(path="$.reworks", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)

### answers
- type: integer
- default: `0`
- required: false
- semantics: number of PM answers the writer used
- verify: json_path(path="$.answers", matches="^[0-9]+$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone` @9c7cde5bf6d0
- tests: `workflows/tests/author/epic_author/test_flow.py::test_a_blocked_writer_is_answered_by_the_pm_then_retries`
- detail: [epic author completion field roles](../concepts/epic-author-done-field-roles.md)
