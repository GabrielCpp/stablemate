---
type: concept
slug: progress-push-documentation-contexts
title: Progress push documentation contexts
---
# Progress push documentation contexts

One progress push is handled by `push_progress`: it rejects an empty normalized container id,
hydrates missing volume metadata, upserts the workflow as running, and broadcasts the updated
dashboard shell. The handler contract and the workflow-state transition are two views of that
one operation, not alternative implementations.

Read [push progress](groom-app-module.md#method-push-progress) when the question concerns the
payload, validation, returned result, metadata resolution, or broadcast. Read
[progress push transition](workflow-state.md#transition-progress-push) when the question
concerns why a workflow becomes `running` and how that lifecycle evidence relates to the other
state transitions. Neither view supersedes the other: a complete understanding of the push uses
the handler for its request behaviour and the transition for its lifecycle consequence.

- code: groom/groom/app.py::push_progress
- rule: use the handler node for request behaviour and the transition node for the resulting workflow-state change; neither is a replacement for the other
