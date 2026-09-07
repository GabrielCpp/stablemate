---
type: format
slug: coder-queue-epic-blocked
title: Coder queue epic blocked
---
# Coder queue epic blocked

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBlocked`
- detail: [coder shared library](concepts/coder-shared-library.md)

The blocked-epic result records that an epic is set aside for the current run while leaving its
queue entry and branch unmerged.

## Fields

### epic_blocked
- type: boolean
- default: `false`
- required: false
- semantics: whether the supplied epic was recorded as blocked
- verify: json_path(path="$.epic_blocked", equals=false)
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBlocked`
- detail: [epic blocked field roles](concepts/epic-blocked-field-roles.md)

### blocked_epics
- type: string
- default: `""`
- required: false
- semantics: comma-joined identifiers in the current run's blocked set
- verify: json_path(path="$.blocked_epics", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBlocked`
- detail: [epic blocked field roles](concepts/epic-blocked-field-roles.md)

### reason
- type: string
- default: `""`
- required: false
- semantics: explanation of the set-aside decision or missing epic input
- verify: json_path(path="$.reason", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/queue.py::EpicBlocked`
- detail: [epic blocked field roles](concepts/epic-blocked-field-roles.md)
