---
type: concept
slug: repo-observation-fields
title: RepoObservation fields
---
# RepoObservation fields

`RepoObservation` records complementary facts reported by Git about one working tree at one
moment; its fields are not alternatives. Read `path` to identify the sampled working tree,
`root` and `origin` for repository identity, `head` and `branch` for revision identity, and
`dirty` for working-tree status. Preserve the complete observation when comparing what a run
started from with what it ended on.

The `RepoObservation` source defines every value as empty or `None` by default: an empty value
means the fact was not observed. In particular, `dirty: None` means Git was not queried or could
not answer, rather than that the tree was clean.

- code: `workhorse/workhorse/records.py::RepoObservation`
- rule: select the field that answers the required point-in-time Git fact; the fields are complementary and none supersedes another
