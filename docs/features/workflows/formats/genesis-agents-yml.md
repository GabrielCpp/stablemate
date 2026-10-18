---
type: format
slug: genesis-agents-yml
title: Genesis agents configuration result
---
# Genesis agents configuration result

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml` @e78de4f5acb0
- detail: [coder genesis bootstrap](../concepts/coder-genesis-bootstrap.md)

The result records the configuration file path, whether the requested merge changed it, and any
operator-facing note.

## Fields

### written
- type: boolean
- default: false
- required: false
- semantics: whether the configuration merge wrote a change
- verify: json_path(path="$.written", equals=true)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml.written` @e78de4f5acb0

### path
- type: string
- default: empty string
- required: false
- semantics: path to the target agents.yml
- verify: json_path(path="$.path", equals="docs/stories/acme-story/story.md")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml.path` @e78de4f5acb0

### note
- type: string
- default: empty string
- required: false
- semantics: explanation of configuration changes or no-op
- verify: json_path(path="$.note", equals="example note")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml.note` @e78de4f5acb0
