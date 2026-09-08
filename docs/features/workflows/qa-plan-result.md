---
type: format
slug: qa-plan-result
title: QA plan result
---
# QA plan result

The verdict `plan-qa.md` and `repair-qa-plan.md` report on the QA test plan authoring and repair — whether the plan is complete and ready to run.

- file: none — agent reply and checkpoint value
- config: `QaPlanResult` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanResult`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `done` or `blocked`
- required: true
- semantics: `done` when the plan is written and ready for execution
- verify: json_path(path="$.status", equals="done")
- semantics: `blocked` when no plan this stage could write would be a real test of the story
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanResult.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what was written or — on a repair — each finding closed and how
- verify: json_path(path="$.notes", matches=".*")
- semantics: on `blocked`, the specific dependency and what was attempted before concluding it
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanResult.notes`

### repaired_scenarios

- type: `list[str]`
- default: empty list
- required: false
- semantics: on a non-repair turn, remains empty
- verify: count(subject="$.repaired_scenarios", equals=0)
- semantics: on a repair turn, the id of every scenario whose code was changed
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanResult.repaired_scenarios`

### proved_scenarios

- type: `list[str]`
- default: empty list
- required: false
- semantics: on a first draft, the ids the turn dry-ran green, riskiest first
- verify: count(subject="$.proved_scenarios", equals=0)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaPlanResult.proved_scenarios`

