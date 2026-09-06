---
type: format
slug: lap
title: Coder repair lap
---
# Coder repair lap

- file: none — in-memory repair-loop ledger
- config: `Lap` development flow state parameter
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::Lap`
- detail: [coder development schema contracts](concepts/coder-dev-schema-contracts.md)

## Fields

### fix_lap
- type: `int`
- default: `0`
- required: false
- semantics: repair laps spent on the current gate failure
- verify: json_path(path="$.fix_lap", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::Lap.fix_lap`

### session_turns
- type: `int`
- default: `1`
- required: false
- semantics: turns spent by the story conversation across implementation and repair
- verify: json_path(path="$.session_turns", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::Lap.session_turns`

### digest
- type: `str`
- default: empty string
- required: false
- semantics: prior failure fingerprint used to detect unchanged repair output
- verify: json_path(path="$.digest", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::Lap.digest`
