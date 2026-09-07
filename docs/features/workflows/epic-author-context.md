---
type: format
slug: epic-author-context
title: Epic author context
---
# Epic author context

The checkpoint context combines the resolved author configuration with the one explicit epic that
this subflow is permitted to author. Configuration paths retain the shared `Config` contract; the
epic fields identify the selected epic and its canonical document locations.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorContext`
- detail: [author configuration](author-config.md)
- detail: [author epic-author subflow](concepts/author-epic-author-subflow.md)

## Fields

### repo_root
- type: string path
- default: `""`
- required: false
- semantics: absolute repository root used for the run's graph and artifact operations
- verify: json_path(path="$.repo_root", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### backlog_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: configured backlog path carried from author configuration
- verify: json_path(path="$.backlog_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### roadmap_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: approved roadmap path supplied to the epic-writing turn
- verify: json_path(path="$.roadmap_path", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### epics_dir
- type: repository-relative string path
- default: `""`
- required: false
- semantics: configured epic root used to resolve the selected epic
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### features_dir
- type: string path
- default: `""`
- required: false
- semantics: feature-book directory exposed as read-only grounding to the writing turn
- verify: json_path(path="$.features_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### layers
- type: list of strings
- default: `[]`
- required: false
- semantics: local-instruction skill paths used as prompt layer hints
- verify: json_path(path="$.layers", matches="^\\[\\]$")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Config`
- detail: [author configuration field origin](concepts/author-config-field-origin.md)

### epic
- type: string
- default: `""`
- required: false
- semantics: canonical Ostler name of the one epic selected for authoring
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorContext`
- detail: [Epic author context field roles](concepts/epic-author-context-field-roles.md)

### epic_dir
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical directory containing the selected epic document
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorContext`
- detail: [Epic author context field roles](concepts/epic-author-context-field-roles.md)

### epic_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: canonical `epic.md` path for the selected epic
- verify: json_path(path="$.epic_path", matches="/epic\\.md$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicAuthorContext`
- tests: `workflows/tests/author/epic_author/test_flow.py::test_authors_only_the_explicit_epic_and_returns_document_evidence`
- detail: [Epic author context field roles](concepts/epic-author-context-field-roles.md)
