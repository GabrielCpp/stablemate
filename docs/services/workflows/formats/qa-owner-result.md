---
type: format
slug: qa-owner-result
title: QA owner result
---
# QA owner result

The verdict the QA owner turn reports on its story, rendered by `qa-story.md`. The flow reruns the plan the owner left and gates these claims before it believes them.

- file: none — agent reply and checkpoint value
- config: `QaOwnerResult` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaOwnerResult` @01bc525fb1ec
- detail: [coder QA schema contracts](../concepts/coder-qa-schema-contracts.md)
- detail: [coder QA flow](../flows/coder-qa.md)

## Fields

### status

- type: literal `passed`, `findings`, or `blocked`
- required: true
- semantics: `passed` when the scored run passed, the auditor's refutation did not stand, and every obligation is covered
- verify: json_path(path="$.status", equals="passed")
- semantics: `findings` when the scored run failed on the product and each failure is one entry in `findings`
- verify: json_path(path="$.status", equals="findings")
- semantics: `blocked` only when something an operator alone can decide stops the turn, since a plan, stack or setup problem is the owner's to repair
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaOwnerResult.status` @01bc525fb1ec

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what the turn planned, repaired and ran, plus on `blocked` the one question that would unblock it
- verify: json_path(path="$.notes", equals="Planned two scenarios and ran the scored plan.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaOwnerResult.notes` @01bc525fb1ec

### findings

- type: list of `QaFinding`
- default: empty list
- required: false
- semantics: one entry per product defect the scored run proved, with the failing scenario and assertion and the smallest product change that would pass it
- verify: json_path(path="$.findings[0].target", equals="src/app.py")
- semantics: empty on `passed` and on `blocked`
- verify: json_path(path="$.findings", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaOwnerResult.findings` @01bc525fb1ec

### proved_scenarios

- type: list of `str`
- default: empty list
- required: false
- semantics: the id of every scenario the turn added or changed and dry-ran green under the scratch directory
- verify: json_path(path="$.proved_scenarios[0]", equals="login-happy-path")
- semantics: the dry-run gate reads the scratch log for each id, so naming a scenario that did not dry-run fails the check
- verify: json_path(path="$.proved_scenarios[1]", equals="logout-clears-session")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaOwnerResult.proved_scenarios` @01bc525fb1ec
