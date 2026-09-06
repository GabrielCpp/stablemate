---
type: format
slug: finding
title: Coder finding
---
# Coder finding

One structured piece of evidence handed to escalation when no downstream fixer owns it. A finding
may omit its target or repair, in which case it remains visible to the operator rather than being
silently discarded.

- file: none — in-memory workflow result
- config: producing coder node evidence
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding`
- detail: [Coder escalation composition](concepts/coder-shared-escalation.md)
- detail: [Coder result routing contract](concepts/coder-result-routing.md)

## Fields

### target
- type: `str`
- default: empty string
- required: false
- semantics: location or identifier where the issue was observed
- verify: json_path(path="$.target", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.target`

### issue
- type: `str`
- default: empty string
- required: false
- semantics: description of the observed problem
- verify: json_path(path="$.issue", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.issue`

### repair
- type: `str`
- default: empty string
- required: false
- semantics: smallest acceptable change when a fixer can act on the finding
- verify: json_path(path="$.repair", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.repair`

## Methods

### actionable
- sig: `Finding.actionable -> bool`
- does: returns true when both target and repair contain non-whitespace text
- verify: json_path(path="$.actionable", equals=true)
- returns: false when either target or repair is empty or whitespace-only
- verify: json_path(path="$.actionable", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::Finding.actionable`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_a_finding_needs_both_a_target_and_a_repair`
