---
type: concept
slug: repository-snapshot-documentation-context
title: Repository snapshot documentation context
---
# Repository snapshot documentation context

Repository observation documents the module's complete diagnostic contract: best-effort Git
facts, the execution scope, and cached boundary observations. Its `RepositorySnapshot` field
describes the immutable collection that `observe_scope` and `HeadWatch.scope` return.

Repository snapshot field selection documents a narrower reading decision within that value.
Use `RepositorySnapshot` when the whole ordered, Git-root-deduplicated scope is needed; use
`directories` when examining the individual `DirectoryObservation` entries. The source defines
`directories` as the sole field of `RepositorySnapshot`, so these documents cover different
contexts of one value rather than competing implementations.

- code: `workhorse/workhorse/gitstate.py::RepositorySnapshot`
- rule: use repository observation for the module-level diagnostic contract and repository snapshot field selection for choosing the whole scope record or its ordered directory entries; neither document supersedes the other
- detail: [Repository snapshot contexts](repository-snapshot-contexts.md)
- detail: [Repository snapshot concept selection](repository-snapshot-concept-selection.md)
