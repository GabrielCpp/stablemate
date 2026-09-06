---
type: format
slug: author-step
title: Author step
---
# Author step

The flat author planner's next artifact-derived operation. `kind` selects one of the six
workflow phases; the remaining strings identify the roadmap, epic, story, and reason for that
operation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### kind
- type: `Literal["milestone", "epic-split", "epic-author", "story-split", "story-author", "finalize"]`
- default: milestone
- required: false
- semantics: phase of the next author operation
- verify: json_path(path="$.kind", equals="milestone")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`

### roadmap
- type: string
- default: empty string
- required: false
- semantics: roadmap associated with the planned operation
- verify: json_path(path="$.roadmap", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`

### epic
- type: string
- default: empty string
- required: false
- semantics: epic associated with the planned operation
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`

### story
- type: string
- default: empty string
- required: false
- semantics: story associated with the planned operation
- verify: json_path(path="$.story", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`

### reason
- type: string
- default: empty string
- required: false
- semantics: planner reason for selecting the operation
- verify: json_path(path="$.reason", matches=".*")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep`
