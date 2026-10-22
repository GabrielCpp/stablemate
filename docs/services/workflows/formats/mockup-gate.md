---
type: format
slug: mockup-gate
title: Mockup gate
---
# Mockup gate

The mockup gate decides whether the current story needs design work. It carries the story's
services and evidence alongside the decision so the checkpoint explains why the gate was or
was not required.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @0c2f7d227faf
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### required
- type: boolean
- default: true
- required: false
- semantics: whether a mockup turn is required before story authoring
- verify: json_path(path="$.required", equals=True)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @0c2f7d227faf
- detail: [mockup gate field roles](../concepts/mockup-gate-field-roles.md)

### services
- type: list of strings
- default: empty list
- required: false
- semantics: the story's services, as book names
- verify: count(subject="services", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @0c2f7d227faf
- detail: [mockup gate field roles](../concepts/mockup-gate-field-roles.md)

### evidence
- type: string
- default: empty string
- required: false
- semantics: source evidence supporting the mockup requirement decision
- verify: json_path(path="$.evidence", equals="example evidence")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate` @0c2f7d227faf
- detail: [mockup gate field roles](../concepts/mockup-gate-field-roles.md)
