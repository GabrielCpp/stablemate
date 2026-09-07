---
type: concept
slug: story-split-result-field-roles
title: Story split result field roles
---
# Story split result field roles

Every `StorySplit` agent result carries both fields; neither is an alternative to the other.
`status` is the routing decision: `standoff` declines the requested rework and sends the result
to the coverage gate, while the remaining values select blocked handling or normal continuation.
`notes` carries the agent's findings for that gate or for the next rework turn. A consumer needs
the status to choose the path and the notes to understand the context carried along it.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/main.py::StorySplit`
- rule: read `status` to select handling and `notes` to retain the agent context; both fields apply to every story-split result
