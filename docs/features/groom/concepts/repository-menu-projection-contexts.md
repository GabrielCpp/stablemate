---
type: concept
slug: repository-menu-projection-contexts
title: Repository menu projection contexts
---
# Repository menu projection contexts

`repo_entries` has one implementation and no caller chooses between alternatives. It accepts the
already-discovered `(workflow, checkout directories)` pairs, sorts them by workflow state and
name, and emits the grouped repository-menu shape. Its loop neither dispatches to another
projection nor retains a legacy branch.

Read [the projection-module method](groom-projection-module.md#method-repo-entries) to understand
how this pure transformation fits with the other dashboard wire projections. Read [the
repository-menu-format method](../repository-menu-data.md#method-repo-entries) to understand the
same callable's input, output, error, and empty-checkout contract. These are complementary
documentation contexts for one callable, not implementations to select between.

- code: groom/groom/projection.py::repo_entries
- rule: choose the documentation context by the contract in question; no implementation ranking exists because both nodes describe the same `repo_entries` callable.
