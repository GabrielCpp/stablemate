---
type: format
slug: genesis-skeleton
title: Genesis skeleton result
---
# Genesis skeleton result

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::Skeleton` @e78de4f5acb0
- detail: [coder genesis bootstrap](../concepts/coder-genesis-bootstrap.md)

The result is successful only when the native initialization leaves the declared marker in
place, regardless of the command's exit status alone.

## Fields

### ok
- type: boolean
- default: false
- required: false
- semantics: whether the service marker proves initialization succeeded
- verify: json_path(path="$.ok", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::Skeleton.ok` @e78de4f5acb0

### note
- type: string
- default: empty string
- required: false
- semantics: initialization explanation or failure detail
- verify: json_path(path="$.note", equals="example note")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::Skeleton.note` @e78de4f5acb0

### marker_path
- type: string
- default: empty string
- required: false
- semantics: path to the marker checked by genesis
- verify: json_path(path="$.marker_path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::Skeleton.marker_path` @e78de4f5acb0
