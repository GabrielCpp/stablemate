---
type: format
slug: qa-run-result
title: QA run result
---
# QA run result

The verdict one QA grading turn reports — rendered by `qa-fix-item.md` and `apply-qa-fixes.md` — whether an acceptance criterion or QA finding passed, failed, or cannot be completed in this repository.

- file: none — agent reply and checkpoint value
- config: `QaRunResult` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaRunResult`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `passed`, `failed`, or `blocked`
- required: true
- semantics: `passed` when every acceptance criterion is verified by something the turn actually ran
- verify: json_path(path="$.status", equals="passed")
- semantics: `failed` when the defect is real, in scope and not fixed
- verify: json_path(path="$.status", equals="failed")
- semantics: `blocked` only when no further attempt in this repository could succeed because what is missing is external
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaRunResult.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what was run, what was observed and what remains
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaRunResult.notes`

