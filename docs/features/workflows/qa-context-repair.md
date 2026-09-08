---
type: format
slug: qa-context-repair
title: QA context repair result
---
# QA context repair result

The verdict `repair-qa-context.md` reports on whether the obligation packet grounding can be repaired so the QA plan rebuilds successfully.

- file: none — agent reply and checkpoint value
- config: `ContextRepair` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ContextRepair`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `repaired` or `blocked`
- required: true
- semantics: `repaired` when the grounding is fixed and the packet can be rebuilt
- verify: json_path(path="$.status", equals="repaired")
- semantics: `blocked` only when the repair needs an author or product decision, or a source repository not given
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ContextRepair.status`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: what was repaired — or, when blocked, what it needs
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::ContextRepair.notes`

