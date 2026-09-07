---
type: format
slug: epic-evidence
title: Epic evidence
---
# Epic evidence

Validation evidence reports whether the explicit epic has its document and at least one researched
seed. It preserves the resolved identity and paths, counts the seeds, and joins validation errors
with newlines for the operator or resolver.

- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- detail: [author epic-author subflow](concepts/author-epic-author-subflow.md)

## Fields

### ok
- type: boolean
- default: `false`
- required: false
- semantics: whether the epic document and researched-seed validation passed without errors
- verify: json_path(path="$.ok", equals=true)
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- detail: [epic evidence field roles](concepts/epic-evidence-field-roles.md)

### epic
- type: string
- default: `""`
- required: false
- semantics: canonical epic name when found, or the requested name when validation cannot resolve it
- verify: json_path(path="$.epic", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- detail: [epic evidence field roles](concepts/epic-evidence-field-roles.md)

### epic_dir
- type: repository-relative string path
- default: `""`
- required: false
- semantics: resolved or attempted directory for the validated epic
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- detail: [epic evidence field roles](concepts/epic-evidence-field-roles.md)

### epic_path
- type: repository-relative string path
- default: `""`
- required: false
- semantics: existing epic document path, or the expected `epic.md` path when absent
- verify: json_path(path="$.epic_path", matches="/epic\\.md$")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- detail: [epic evidence field roles](concepts/epic-evidence-field-roles.md)

### seed_count
- type: integer
- default: `0`
- required: false
- semantics: number of researched seeds found on the epic
- verify: json_path(path="$.seed_count", matches=".+")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- detail: [epic evidence field roles](concepts/epic-evidence-field-roles.md)

### errors
- type: newline-separated string
- default: `""`
- required: false
- semantics: validation findings, one error per line, empty when validation succeeds
- verify: json_path(path="$.errors", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_author/schemas.py::EpicEvidence`
- tests: `workflows/tests/author/epic_author/test_flow.py::test_document_validation_uses_epic_md_and_seed_evidence`
- detail: [epic evidence field roles](concepts/epic-evidence-field-roles.md)
