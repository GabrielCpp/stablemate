---
type: concept
slug: partition-check-field-roles
title: Partition check field roles
---
# Partition check field roles

`PartitionCheck` reports one deterministic validation outcome in two complementary
fields. `partition_ok` is the boolean gate that records whether the cluster file
covers every finding it claims. `partition_errors` carries the diagnostic text when
that validation does not hold.

Read `partition_ok` to make the branch decision, then read `partition_errors` to
diagnose a failed validation. Neither field replaces or ranks above the other: the
schema declares both as current outputs of `validate_partition`.

- code: `workflows/src/workhorse_workflows/author/shared/schemas/survey.py::PartitionCheck`
- rule: use `partition_ok` for the validation decision and `partition_errors` for its diagnostic detail
