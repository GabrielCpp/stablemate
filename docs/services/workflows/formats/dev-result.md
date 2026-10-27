---
type: format
slug: dev-result
title: Coder development outcome
---
# Coder development outcome

- file: none — in-memory development-flow result
- config: `DevOutcome` parent-flow handoff
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevOutcome` @4ed65104b9b1
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)
- detail: [coder development story result](dev-story-result.md)

## Fields

### status
- type: literal `ready` or `replan`
- default: `ready`
- required: false
- semantics: whether development is ready for the next lane or requires replanning
- verify: json_path(path="$.status", matches="ready|replan")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevOutcome.status` @4ed65104b9b1

### operator_notes
- type: `str`
- default: empty string
- required: false
- semantics: operator answer text passed back to the parent flow
- verify: json_path(path="$.operator_notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevOutcome.operator_notes` @4ed65104b9b1

### settled
- type: list of `str`
- default: empty list
- required: false
- semantics: ids of review findings the settlement ledger holds as fixed with evidence
- verify: json_path(path="$.settled", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevOutcome.settled` @4ed65104b9b1

### declined
- type: list of `str`
- default: empty list
- required: false
- semantics: ids of review findings the dev owner declined with a reason
- verify: json_path(path="$.declined", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevOutcome.declined` @4ed65104b9b1
