---
type: concept
slug: implementation-result-status
title: Implementation result status
---
# Implementation result status

`ImplResult.status` is one required, closed result field shared by implement and review-apply
turns. Its value reports what the turn says it did; downstream gates decide whether the reported
success states are accepted, while `blocked` is the pessimistic state that can route the workflow
to a block.

The two field nodes are not alternative implementations and neither supersedes the other. Use
the implementation-result field when reading or producing the shared output contract for an
implementation turn. Use the apply-review-prompt field when authoring or interpreting a
review-apply turn, where deterministic settlement checks the result before accepting it. Both
contexts use the same five values: `done`, `applied`, `no_changes_needed`, `needs_changes`, and
`blocked`.

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev.py::ImplResult.status`
- rule: select the field node by the turn context; neither is a preferred or deprecated implementation
