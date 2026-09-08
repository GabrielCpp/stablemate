---
type: concept
slug: parity-surveyor-concept-selection
title: Parity surveyor concept selection
---
# Parity surveyor concept selection

`workflows/src/workhorse_workflows/author/parity_surveyor/flow.py::ParitySurveyor` is the only
implementation of the parity-surveyor subflow: a single class that freezes the baseline into a
unit list, walks each unit through pick-assess-mark, verifies coverage, and emits one backlog
bullet per uncovered surface. Three concept nodes ground themselves in that symbol and document
it from different angles; no part of the source records a preference, so the selection rule lives
here.

Use [parity surveyor subflow](parity-surveyor-subflow.md) for the flow lifecycle, the
`baseline_inventory` and `survey_dir` fields, every state-machine method, and the helper nodes
the class calls — it is the comprehensive view of the workflow.

Use [parity surveyor input roles](parity-surveyor-input-roles.md) when the question is whether
to set `baseline_inventory` or `survey_dir`, whether one substitutes for the other, or what each
input is for — it is the input-roles view, not a duplicate of the subflow.

[Author parity surveyor subflow](author-parity-surveyor-subflow.md) covers a subset of the same
methods without the `## Fields` section or the helper-node signatures, and is superseded by the
comprehensive subflow concept above.

- rule: reach for the parity-surveyor-subflow concept for the flow lifecycle, fields, and methods; reach for the parity-surveyor-input-roles concept when choosing between baseline_inventory and survey_dir; the author-prefixed subflow concept is superseded
- prefers: [parity surveyor subflow](parity-surveyor-subflow.md)
- deprecates: [author parity surveyor subflow](author-parity-surveyor-subflow.md)