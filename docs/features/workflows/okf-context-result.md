---
type: format
slug: okf-context-result
title: Coder OKF context result
---
# Coder OKF context result

- file: none — in-memory result returned by the OKF context build and validation nodes
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/okf.py::OkfContextResult`
- detail: [coder shared OKF context](concepts/coder-shared-okf-context.md)
- tests: `workflows/tests/coder/shared/test_okf_memo.py::test_a_repeat_visit_reuses_the_packet_byte_for_byte`

The result carries the context packet's gate verdict, a diagnostic note, and the raw Ostler
payload. Its status is closed: `passed` means the relevant context operation succeeded, while
`invalid` is the conservative result for every other outcome.

## Fields

### status
- type: literal `passed` or `invalid`
- default: `invalid`
- required: false
- semantics: context build or validation verdict
- verify: json_path(path="$.status", matches="passed|invalid")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/okf.py::OkfContextResult.status`

### notes
- type: `str`
- default: empty string
- required: false
- semantics: diagnostic summary associated with the context operation
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/okf.py::OkfContextResult.notes`

### ostler
- type: `dict[str, Any]`
- default: empty mapping
- required: false
- semantics: raw Ostler context output consumed by downstream gates
- verify: json_path(path="$.ostler", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/okf.py::OkfContextResult.ostler`
