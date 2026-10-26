---
type: format
slug: coder-queue-epic-pruned
title: Coder queue epic pruned
---
# Coder queue epic pruned

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPruned` @5263a86ab920
- detail: [coder shared library](../concepts/coder-shared-library.md)

The prune result records whether the merged epic was removed from the active queue. The prune
tries the ostler-managed queue first and falls back to the legacy JSON queue file, and an
explicit sidecar path is pruned in place. A removal commits the changed queue file on the current
branch. A missing epic name, or an epic the queue does not hold, is a no-op rather than a failure.

## Fields

### pruned
- type: boolean
- default: `false`
- required: false
- semantics: whether an epic entry was removed from the queue and the removal committed
- verify: json_path(path="$.pruned", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicPruned` @5263a86ab920
