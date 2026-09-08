---
type: concept
slug: epic-split-prompt-args
title: Epic split prompt args
---
# Epic split prompt args

`EpicSplit._split_args` in
`workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` is the one
builder for the `roadmap`, `milestone`, `epics_dir`, and `review_notes` template arguments shared
by the split, review, and rework turns. `start` and `review` call it with no argument, so
`review_notes` renders as the empty string on both; `rework` calls it with the accumulated review
notes, so `review_notes` renders populated there. `resolve` calls it too, then layers
`context_path` and `block_notes` on top for the operator-resolution turn.

This is not a competition between implementations: every `field` node across
[split-epics](../author-split-epics-prompt.md), [review-epic-split](../author-review-epic-split-prompt.md),
and [rework-epic-split](../author-rework-epic-split-prompt.md) that cites `_split_args` as its
`code:` is documenting the same value, produced by the same call, for a different prompt render.
`roadmap`, `milestone`, and `epics_dir` are identical across all three turns because they are the
same immutable context fields; only `review_notes` differs, and each of those three docs states
its own turn-specific semantics for it — empty on `start`/`review`, populated on `rework`.

- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args`
- rule: `roadmap`, `milestone`, and `epics_dir` are one shared value produced by `_split_args` for
  every turn; `review_notes` is the one field that varies by call site, and each prompt doc states
  its own value for it

