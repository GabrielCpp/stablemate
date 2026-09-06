---
type: format
slug: merge-fix-result
title: Merge fix result
---
# Merge fix result

- file: none — an in-memory agent reply consumed by the merge-fix workflow
- config: none — the status and notes are supplied by the fixing agent
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeFixResult`
- detail: [coder main PR boundary](concepts/coder-main-pr-boundary.md)

The result records the agent's merge-conflict resolution outcome and its explanation. The status
is required because this is the module's agent-produced verdict; no default may silently choose an
outcome.

## Fields

### status

- type: `Literal["fixed", "failed", "blocked"]`
- required: true
- semantics: `fixed` means the resolution was committed and the branches now merge cleanly
- semantics: `failed` means this attempt did not finish but another attempt may succeed
- semantics: `blocked` means resolving requires an operator decision, a history rewrite, or access to an unavailable repository
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeFixResult.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what was resolved, or on a blocked result the files, unavailable decision, and first attempted action
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/pr.py::MergeFixResult.notes`
