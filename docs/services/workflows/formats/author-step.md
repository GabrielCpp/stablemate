---
type: format
slug: author-step
title: Author step
---
# Author step

The flat author planner's next artifact-derived operation. `kind` selects one of the five
workflow phases; the remaining strings identify the milestone, epic, story, and reason for that
operation.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @2e101dbcac2e
- detail: [author shared schemas](../concepts/author-shared-schemas.md)

## Fields

### kind
- type: `Literal["epic-split", "epic-author", "story-split", "story-author", "finalize"]`
- default: epic-split
- required: false
- semantics: phase of the next author operation
- verify: json_path(path="$.kind", equals="epic-split")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @2e101dbcac2e
- detail: [author step field roles](../concepts/author-step-field-roles.md)

### milestone
- type: string
- default: empty string
- required: false
- semantics: approved milestone associated with the planned operation
- verify: json_path(path="$.milestone", equals="docs/milestones/acme-launch/milestone.md")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @2e101dbcac2e
- detail: [author step field roles](../concepts/author-step-field-roles.md)

### epic
- type: string
- default: empty string
- required: false
- semantics: epic associated with the planned operation
- verify: json_path(path="$.epic", equals="acme-epic")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @2e101dbcac2e
- detail: [author step field roles](../concepts/author-step-field-roles.md)

### story
- type: string
- default: empty string
- required: false
- semantics: story associated with the planned operation
- verify: json_path(path="$.story", equals="acme-story")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @2e101dbcac2e
- detail: [author step field roles](../concepts/author-step-field-roles.md)

### reason
- type: string
- default: empty string
- required: false
- semantics: planner reason for selecting the operation
- verify: json_path(path="$.reason", equals="The slice works without it.")
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::AuthorStep` @2e101dbcac2e
- detail: [author step field roles](../concepts/author-step-field-roles.md)
