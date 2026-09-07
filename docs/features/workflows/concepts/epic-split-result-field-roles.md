---
type: concept
slug: epic-split-result-field-roles
title: Epic split result field roles
---
# Epic split result field roles

`workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult` declares
`status` and `notes` as separate required fields. They are complementary rather than competing
implementations: the reply is incomplete to a reader who examines only one.

Read `status` to determine whether the split completed or is blocked. Read `notes` to learn the
agent's explanation for review or operator resolution. Neither field is preferred or deprecated;
each answers a different question about the same turn.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitResult`
- rule: use `status` for the outcome and `notes` for its explanation; read both to understand the reply
