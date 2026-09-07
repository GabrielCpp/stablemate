---
type: format
slug: epic-choice
title: Epic choice
---
# Epic choice

The deterministic epic selectors return this shape. Every field is optional at the model boundary
because the schema supplies an empty or false default; a selected result fills the selection fields,
while an empty or failed selection carries only its reason and any available progress.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- detail: [Author main epic selection](concepts/author-main-epic-selection.md)

## Fields

### has_epic
- type: boolean
- default: `false`
- required: false
- semantics: whether the result contains an epic selected for authoring
- verify: json_path(path="$.has_epic", equals=true)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- detail: [Epic choice field roles](concepts/epic-choice-field-roles.md)

### epic
- type: string
- default: `""`
- required: false
- semantics: the Ostler-resolved numbered epic directory name when an epic is selected
- verify: json_path(path="$.epic", matches="^\\d{4}-.+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- detail: [Epic choice field roles](concepts/epic-choice-field-roles.md)

### epic_dir
- type: string
- default: `""`
- required: false
- semantics: the repository-relative directory used by later author nodes for the selected epic
- verify: json_path(path="$.epic_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- detail: [Epic choice field roles](concepts/epic-choice-field-roles.md)

### reason
- type: string
- default: `""`
- required: false
- semantics: the selection, completion, empty-queue, or worklist-failure explanation
- verify: json_path(path="$.reason", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- detail: [Epic choice field roles](concepts/epic-choice-field-roles.md)

### progress
- type: string
- default: `""`
- required: false
- semantics: the worklist snapshot rendered before a completed or selected result is returned
- verify: json_path(path="$.progress", matches=".+")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::EpicChoice`
- detail: [Epic choice field roles](concepts/epic-choice-field-roles.md)
