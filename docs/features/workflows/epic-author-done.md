---
type: format
slug: epic-author-done
title: Epic author completion
---
# Epic author completion

The terminal result marks completion of authoring one explicit epic after document validation. It
returns the validated epic identity, its canonical paths, the researched-seed count, and the number
of automatic operator resolutions used before success.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- detail: [author epic-author subflow](concepts/author-epic-author-subflow.md)

## Fields

### status
- type: literal string `authored`
- default: `"authored"`
- required: false
- semantics: terminal status stating that the explicit epic crossed the authoring boundary
- verify: json_path(path="$.status", equals="authored")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- detail: [epic author completion field roles](concepts/epic-author-done-field-roles.md)

### epic
- type: string
- default: `""`
- required: false
- semantics: validated canonical name of the authored epic
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- detail: [epic author completion field roles](concepts/epic-author-done-field-roles.md)

### epic_dir
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical directory containing the authored epic
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- detail: [epic author completion field roles](concepts/epic-author-done-field-roles.md)

### epic_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical `epic.md` path validated before completion
- verify: json_path(path="$.epic_path", matches="/epic\\.md$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- detail: [epic author completion field roles](concepts/epic-author-done-field-roles.md)

### seed_count
- type: integer
- default: `0`
- required: false
- semantics: number of researched seeds present in the completed epic
- verify: json_path(path="$.seed_count", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- detail: [epic author completion field roles](concepts/epic-author-done-field-roles.md)

### operator_resolutions
- type: integer
- default: `0`
- required: false
- semantics: number of automatic resolution turns used before the successful completion
- verify: json_path(path="$.operator_resolutions", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorDone`
- tests: `workflows/tests/author/epic_author/test_flow.py::test_block_is_diagnosed_then_retries_the_same_epic`
- detail: [epic author completion field roles](concepts/epic-author-done-field-roles.md)
