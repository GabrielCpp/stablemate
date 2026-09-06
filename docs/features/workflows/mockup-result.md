---
type: format
slug: mockup-result
title: Mockup result
---
# Mockup result

The design agent reply records the outcome, chosen surface, mockup text, and notes for a story
that requires a surface sketch.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### status
- type: string
- default: empty string
- required: false
- semantics: agent-reported outcome of designing the mockup
- verify: json_path(path="$.status", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`

### surface
- type: string
- default: empty string
- required: false
- semantics: product surface represented by the mockup
- verify: json_path(path="$.surface", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`

### mockup
- type: string
- default: empty string
- required: false
- semantics: surface sketch returned for story authoring
- verify: json_path(path="$.mockup", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`

### notes
- type: string
- default: empty string
- required: false
- semantics: design notes accompanying the mockup
- verify: json_path(path="$.notes", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::MockupResult`
