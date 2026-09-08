---
type: concept
slug: repository-snapshot-field-selection
title: Repository snapshot field selection
---
# Repository snapshot field selection

`RepositorySnapshot` and `directories` are complementary views of the same immutable scope
observation, not alternative implementations. `observe_scope` constructs one
`RepositorySnapshot` from the ordered, Git-root-deduplicated directory observations. Select
`RepositorySnapshot` when the complete immutable scope record is the value in question; select
`directories` when reading its ordered `DirectoryObservation` entries. Neither view supersedes
the other.

- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot`
- rule: select `RepositorySnapshot` for the complete immutable scope record and `directories` for its ordered entries; the views are complementary and have no ranking or replacement relationship
- detail: [Repository snapshot contexts](repository-snapshot-contexts.md)
- detail: [Repository snapshot concept selection](repository-snapshot-concept-selection.md)
- detail: [Repository snapshot documentation context](repository-snapshot-documentation-context.md)
