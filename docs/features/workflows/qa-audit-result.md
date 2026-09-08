---
type: format
slug: qa-audit-result
title: QA audit result
---
# QA audit result

The verdict `audit-qa.md` reports on an adversarial second read of a QA pass that already cleared the gate — whether the pass survives independent scrutiny.

- file: none — agent reply and checkpoint value
- config: `QaAudit` agent-turn output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit`
- detail: [coder QA schema contracts](concepts/coder-qa-schema-contracts.md)

## Fields

### status

- type: literal `audited` or `blocked`
- required: true
- semantics: `audited` when a verdict on the evidence is reached
- verify: json_path(path="$.status", equals="audited")
- semantics: `blocked` when there was no evidence to judge
- verify: json_path(path="$.status", equals="blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit.status`

### verdict

- type: literal `stands` or `refuted`
- required: false (read only on refusal)
- semantics: `stands` when the pass survives an adversarial second read
- verify: json_path(path="$.verdict", equals="stands")
- semantics: `refuted` when independent scrutiny finds the pass is wrong
- verify: json_path(path="$.verdict", equals="refuted")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit.verdict`

### refutation_class

- type: literal `none`, `product-contradiction`, `plan-defect`, or `evidence-defect`
- required: false (read only on refusal)
- semantics: `none` only when the pass stands cleanly
- verify: json_path(path="$.refutation_class", equals="none")
- semantics: `product-contradiction` when the story itself is wrong
- verify: json_path(path="$.refutation_class", equals="product-contradiction")
- semantics: `plan-defect` when the plan has a defect
- verify: json_path(path="$.refutation_class", equals="plan-defect")
- semantics: `evidence-defect` when the evidence itself is defective
- verify: json_path(path="$.refutation_class", equals="evidence-defect")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit.refutation_class`

### findings

- type: `list[QaFinding]`
- default: empty list
- required: false
- semantics: empty list when the pass stands
- verify: count(subject="$.findings", equals=0)
- semantics: at least one finding when the audit refutes the result
- verify: json_path(path="$.findings[0].target", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit.findings`

### notes

- type: `str`
- default: empty string
- required: false
- semantics: a summary of the findings, in one or two sentences
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/qa.py::QaAudit.notes`

