---
type: format
slug: epic-target
title: Epic target
---
# Epic target

The target is the normalized identity returned after the caller's explicit epic name is resolved
through Ostler. It carries the canonical epic directory and `epic.md` path used by later states.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicTarget`
- detail: [author epic-author subflow](concepts/author-epic-author-subflow.md)

## Fields

### epic
- type: string
- default: `""`
- required: false
- semantics: canonical Ostler name of the explicitly requested epic
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicTarget`

### epic_dir
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical directory resolved for the requested epic
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicTarget`

### epic_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical `epic.md` path beneath the resolved epic directory
- verify: json_path(path="$.epic_path", matches="/epic\\.md$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicTarget`
- tests: `workflows/tests/author/epic_author/test_flow.py::test_authors_only_the_explicit_epic_and_returns_document_evidence`
