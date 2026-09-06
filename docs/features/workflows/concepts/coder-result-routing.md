---
type: concept
slug: coder-result-routing
title: Coder result routing contract
---
# Coder result routing contract

The coder schema base gives every result a common way to distinguish a genuine operator block
from an ordinary pessimistic or incomplete result. All concrete results ignore unknown input
keys and remove dictionary entries whose value is `null` before validation; fields declared with
defaults therefore retain those defaults when a Python-produced node emits null output. An
agent-produced required status still fails validation when omitted, which causes the runner to
retry rather than silently select an arm.

A result is blocked only when its own status is one of the four closed agent-status spellings. A
result's actionable findings are the subset that names both a target and a repair; an empty
subset routes the block to the operator rather than sending a complaint around the repair loop
again. `blocked` is derived from the status and is not an independent result field, so a failed
Python node's pessimistic default does not become an operator block.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::__all__`
- detail: [Coder finding](../finding.md)

## Fields

### BLOCKED_STATUSES
- type: `frozenset[str]`
- default: `blocked | unfixable | not_passed | invalid`
- required: true
- semantics: the complete set of status values that make a coder result blocked after surrounding whitespace is removed and case is ignored
- verify: count(subject="blocked status vocabulary", equals=1)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::BLOCKED_STATUSES`

The set is the shared closed vocabulary for agent-produced terminal blocks. It unifies the
spellings that arose in the development, documentation, QA, and planning lanes; deterministic
validators keep their own verdict vocabularies because they are not agent-produced statuses.

## Methods

### CoderResult.blocked
- sig: `CoderResult.blocked -> bool`
- does: returns true when the result exposes a status whose normalized value is in BLOCKED_STATUSES
- verify: json_path(path="$.blocked", equals=true)
- does: returns false when the result has no status or its normalized status is outside BLOCKED_STATUSES
- verify: json_path(path="$.blocked", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::CoderResult.blocked`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_every_spelling_of_giving_up_reads_as_blocked`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_an_unanswered_node_is_not_blocked`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_blocked_ignores_case_and_surrounding_space`

`CoderResult` inherits the shared result normalization: unknown keys are ignored and null values
are removed before its concrete fields validate. This lets Python-produced fields fall back to
their declared pessimistic defaults, while required agent fields remain absent and trigger the
normal parse-retry path.

### CoderResult.actionable
- sig: `CoderResult.actionable -> list[Finding]`
- does: reads the subclass findings collection when present
- verify: json_path(path="$.actionable", matches=".*")
- does: keeps only findings that are Finding instances with actionable target and repair text
- verify: json_path(path="$.actionable", matches=".*")
- returns: an empty list when the result has no actionable finding
- verify: json_path(path="$.actionable", equals=[])
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/_base.py::CoderResult.actionable`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_actionable_keeps_only_the_findings_a_fixer_could_act_on`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_a_block_with_no_evidence_is_a_block_with_nothing_to_route`
- tests: `workflows/tests/coder/shared/test_blocked_signal.py::test_the_narrowed_finding_lists_still_answer_actionable`
