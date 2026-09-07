---
type: concept
slug: partition-proposal-field-roles
title: Partition proposal field roles
---
# Partition proposal field roles

`PartitionProposal` reports one survey partitioning reply in two complementary fields.
`status` records whether the proposal is `complete` or `blocked`, so the workflow can route a
blocked proposal to the operator gate. `notes` carries the partition explanation or blocking
information needed to understand that outcome.

Read `status` to select the outcome path, then read `notes` when the outcome needs explanation.
Neither field replaces or ranks above the other: the schema declares both as current outputs of
the partition-findings prompt.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionProposal`
- rule: use `status` for outcome routing and `notes` for partition explanation or blocking information
