---
type: concept
slug: epic-split-context-field-roles
title: Epic split context field roles
---
# Epic split context field roles

`EpicSplitContext` is one immutable boundary for an epic-split turn, not a choice among
interchangeable field implementations. Its declaration in
`workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext` holds the
repository root, approved roadmap, epic directory, and selected milestone path together with the
pre-split epic names, milestone and epic fingerprints, seed identities, and story slugs.

`prepare_epic_split` in
`workflows/src/workhorse_workflows/author/epic_split/nodes/epics.py::prepare_epic_split` captures
each value from the same surveyed repository and approved milestone before the turn starts. No
field replaces or ranks above another: the location fields identify the approved split input, while
the collection and fingerprint fields preserve the graph snapshot used to reject collateral edits.

- code: `workflows/src/workhorse_workflows/author/epic_split/schemas.py::EpicSplitContext`
- rule: use every field as its distinct part of the one pre-split context; no field is an alternative to another
