---
type: format
slug: gate-list
title: Coder gate list
---
# Coder gate list

- file: none — in-memory declared-gates prompt value
- config: `GateList` gate summary
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateList` @b6e19c205b4f
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### gates
- type: `list[str]`
- default: empty list
- required: false
- semantics: adopted gate names
- verify: json_path(path="$.gates", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateList.gates` @b6e19c205b4f

### commands
- type: `list[str]`
- default: empty list
- required: false
- semantics: commands corresponding to the adopted gates
- verify: json_path(path="$.commands", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateList.commands` @b6e19c205b4f

### text
- type: `str`
- default: empty string
- required: false
- semantics: rendered gate summary, explicitly stating when none are declared
- verify: json_path(path="$.text", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::GateList.text` @b6e19c205b4f
