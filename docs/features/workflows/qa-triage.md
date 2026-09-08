---
type: format
slug: qa-triage
title: QA triage result
---
# QA triage result

The verdict `triage-qa.md` reports on whether QA findings are in-acceptance-criterion fixes or require a scope change to the story.

- file: none — agent reply and checkpoint value
- config: `QaTriage` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaTriage`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `triaged` or `blocked`
- required: true
- semantics: `triaged` when findings are sorted into repair lanes
- verify: json_path(path="$.status", equals="triaged")
- semantics: `blocked` when findings cannot be sorted at all
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaTriage.status`

### triage_action

- type: literal `rescope` or `qa_fix`
- required: false (read only on refusal)
- semantics: `rescope` only if acceptance criteria are amended and budget remains
- verify: json_path(path="$.triage_action", equals="rescope")
- semantics: `qa_fix` when every finding is purely in-acceptance-criterion
- verify: json_path(path="$.triage_action", equals="qa_fix")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaTriage.triage_action`

### qa_failure_class

- type: literal `code`, `product`, `evidence`, or `environment`
- required: false (read only on refusal)
- semantics: `code` when a QA-side code or test change is needed
- verify: json_path(path="$.qa_failure_class", equals="code")
- semantics: `product` when the product itself does not meet an acceptance criterion
- verify: json_path(path="$.qa_failure_class", equals="product")
- semantics: `evidence` when product code is correct and gates are green but evidence work remains
- verify: json_path(path="$.qa_failure_class", equals="evidence")
- semantics: `environment` when the stack, fixtures or emulator must be repaired
- verify: json_path(path="$.qa_failure_class", equals="environment")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaTriage.qa_failure_class`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: read on refusal — what stopped the triager from sorting findings
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaTriage.notes`

