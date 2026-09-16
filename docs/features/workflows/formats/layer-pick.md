---
type: format
slug: layer-pick
title: Coder layer pick
---
# Coder layer pick

- file: none — in-memory layer selection result
- config: `LayerPick` next-layer result
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::LayerPick` @b6e19c205b4f
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)

## Fields

### has_layer
- type: `bool`
- default: `false`
- required: false
- semantics: whether another dispatch entry remains
- verify: json_path(path="$.has_layer", matches="true|false")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::LayerPick.has_layer` @b6e19c205b4f

### index
- type: `int`
- default: `-1`
- required: false
- semantics: selected dispatch position, unchanged when exhausted
- verify: json_path(path="$.index", matches="-?[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::LayerPick.index` @b6e19c205b4f

### layer
- type: `DispatchEntry`
- default: empty dispatch entry
- required: false
- semantics: selected implementation layer
- verify: json_path(path="$.layer", matches=".*")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::LayerPick.layer` @b6e19c205b4f

### dispatch_count
- type: `int`
- default: `0`
- required: false
- semantics: number of dispatch entries considered
- verify: json_path(path="$.dispatch_count", matches="[0-9]+")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::LayerPick.dispatch_count` @b6e19c205b4f
