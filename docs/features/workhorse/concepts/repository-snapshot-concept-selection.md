---
type: concept
slug: repository-snapshot-concept-selection
title: Repository snapshot concept selection
---
# Repository snapshot concept selection

`RepositorySnapshot` is the immutable scope value returned by `observe_scope` and cached by
`HeadWatch.scope`; its only declared field is the ordered tuple of `DirectoryObservation` values.
The module-level repository observation also covers best-effort Git facts and cache boundaries,
while field selection covers reading either the complete snapshot or its entries. These are
complementary documentation contexts for one value, not alternative implementations.

- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot`
- rule: use repository observation for the module-level diagnostic contract, repository snapshot documentation context for its scope-returning operations, and repository snapshot field selection to choose the complete record or its ordered entries; no context supersedes another
- detail: [Repository snapshot contexts](repository-snapshot-contexts.md)
