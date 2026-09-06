---
type: format
slug: fix-ci-result
title: CI fixer result
---
# CI fixer result

The structured report returned by the `fix-ci` agent turn describes whether it repaired the
failing branch, could not repair this attempt, or is blocked by a dependency the repository cannot
change. The flow acts only on `blocked`; the next poll judges `fixed` and `failed`.

- file: none — the report is an agent response, not a persisted file format
- config: none — its values come from the prompt output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::FixCiResult`
- detail: [coder CI remediation flow](flows/fix-ci-remediation.md)
- tests: `workflows/tests/coder/fix_ci/test_flow.py::test_a_fixer_that_says_it_cannot_stops_the_laps_instead_of_re_asking_it`

## Fields

### status

- type: `Literal["fixed", "failed", "blocked"]`
- default: none; the agent must return it
- required: true
- semantics: `fixed` claims a local repair and commit; `failed` requests another attempt; `blocked` says another attempt cannot make CI green without an unavailable dependency or contract change
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::FixCiResult.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: changes made or the specific attempted dependency and reason for failure/blocking
- verify: json_path(path="$.notes", matches="/.+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/ci.py::FixCiResult.notes`
