---
type: format
slug: pruned
title: Pruned backlog result
---
# Pruned backlog result

The story-mode backlog pruning result records how many entries were removed and how many remain.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Pruned`
- detail: [author shared schemas](concepts/author-shared-schemas.md)

## Fields

### removed
- type: integer
- default: 0
- required: false
- semantics: number of backlog bullets removed by the operation
- verify: json_path(path="$.removed", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Pruned`
- detail: [pruned backlog counters](concepts/pruned-backlog-counters.md)

### remaining
- type: integer
- default: 0
- required: false
- semantics: number of backlog bullets remaining after pruning
- verify: json_path(path="$.remaining", equals=0)
- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::Pruned`
- detail: [pruned backlog counters](concepts/pruned-backlog-counters.md)
