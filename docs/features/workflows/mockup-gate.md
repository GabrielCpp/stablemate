---
type: format
slug: mockup-gate
title: Mockup gate
---
# Mockup gate

The mockup gate decides whether the current story needs design work. It carries the seed-derived
layer and service evidence alongside the decision so the checkpoint explains why the gate was or
was not required.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### required
- type: boolean
- default: true
- required: false
- semantics: whether a mockup turn is required before story authoring
- verify: json_path(path="$.required", equals=True)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`

### layers
- type: list of strings
- default: empty list
- required: false
- semantics: union of implementation layers declared by the story's covered seeds
- verify: json_path(path="$.layers", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`

### services
- type: list of strings
- default: empty list
- required: false
- semantics: union of services declared by the story's covered seeds
- verify: json_path(path="$.services", equals=[])
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`

### evidence
- type: string
- default: empty string
- required: false
- semantics: source evidence supporting the mockup requirement decision
- verify: json_path(path="$.evidence", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupGate`
