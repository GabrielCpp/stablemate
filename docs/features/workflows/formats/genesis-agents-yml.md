---
type: format
slug: genesis-agents-yml
title: Genesis agents configuration result
---
# Genesis agents configuration result

- file: none — in-memory genesis result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml` @24e0e633fcd0
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
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml.written` @24e0e633fcd0

### path
- type: string
- default: empty string
- required: false
- semantics: path to the target agents.yml
- verify: json_path(path="$.path", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml.path` @24e0e633fcd0

### note
- type: string
- default: empty string
- required: false
- semantics: explanation of configuration changes or no-op
- verify: json_path(path="$.note", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/genesis.py::AgentsYml.note` @24e0e633fcd0
