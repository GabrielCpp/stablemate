---
type: concept
slug: repository-snapshot-contexts
title: Repository snapshot contexts
---
# Repository snapshot contexts

`RepositorySnapshot` has one implementation: an immutable record whose sole field is the ordered
tuple of `DirectoryObservation` values. `observe_scope` constructs that record, and
`HeadWatch.scope` caches and returns it. The documents grounded to the class therefore describe
different reading contexts for the same value; they do not identify alternative implementations.

Use repository observation for the module-wide diagnostic and caching contract. Use repository
snapshot concept selection for a concise map among these documentation contexts, repository
snapshot documentation context for the boundary between the module and its scope value, and
repository snapshot field selection when choosing between the complete record and its
`directories` entries. No context is preferred or deprecated because the source declares no
second implementation or supersession path.

- rule: choose the document matching the required context; all describe one `RepositorySnapshot` implementation, so none supersedes another
