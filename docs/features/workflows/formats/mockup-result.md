---
type: format
slug: mockup-result
title: Mockup result
---
# Mockup result

The design agent reply records the outcome, chosen surface, mockup text, and notes for a story
that requires a surface sketch.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @2bce00d7c202
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: agent-reported outcome of designing the mockup
- verify: json_path(path="$.status", equals="example status")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @2bce00d7c202
- detail: [mockup result field roles](../concepts/mockup-result-field-roles.md)

### surface
- type: string
- default: empty string
- required: false
- semantics: product surface represented by the mockup
- verify: json_path(path="$.surface", equals="example surface")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @2bce00d7c202
- detail: [mockup result field roles](../concepts/mockup-result-field-roles.md)

### mockup
- type: string
- default: empty string
- required: false
- semantics: surface sketch returned for story authoring
- verify: json_path(path="$.mockup", equals="example mockup")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @2bce00d7c202
- detail: [mockup result field roles](../concepts/mockup-result-field-roles.md)

### notes
- type: string
- default: empty string
- required: false
- semantics: design notes accompanying the mockup
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult` @2bce00d7c202
- detail: [mockup result field roles](../concepts/mockup-result-field-roles.md)
