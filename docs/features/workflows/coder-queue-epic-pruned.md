---
type: format
slug: coder-queue-epic-pruned
title: Coder queue epic pruned
---
# Coder queue epic pruned

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPruned`
- detail: [coder shared library](concepts/coder-shared-library.md)

The prune result records whether the merged epic was removed from the active queue. Missing or
unwritable queue state is a best-effort no-op rather than a failure.

## Fields

### pruned
- type: boolean
- default: `false`
- required: false
- semantics: whether an epic entry was removed from the queue
- verify: json_path(path="$.pruned", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPruned`
