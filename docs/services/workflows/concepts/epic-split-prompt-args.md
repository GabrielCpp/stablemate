---
type: concept
slug: epic-split-prompt-args
title: Epic split prompt args
---
# Epic split prompt args

`EpicSplit._split_args` in
`workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` is the one
builder for the `milestone`, `epics_dir`, `review_notes`, `note` and `ledger` template arguments
shared by the split and rework turns. `start` calls it with a note only, so `review_notes` renders
as the empty string there. `rework` calls it with the accumulated review notes, so `review_notes`
renders populated there. The review is no longer a prompt of this flow: the
[PM review](author-pm-review.md) reads the milestone and the epics itself.

This is not a competition between implementations: every `field` node across
[split-epics](../formats/author-split-epics-prompt.md) and
[rework-epic-split](../formats/author-rework-epic-split-prompt.md) that cites `_split_args` as its
`code:` is documenting the same value, produced by the same call, for a different prompt render.
`milestone`, `epics_dir` and `ledger` are identical across both turns because they are the same
immutable context fields; only `review_notes` and `note` differ, and each of those two docs states
its own turn-specific semantics for them.

- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit._split_args` @978c83a852f4
- rule: `milestone`, `epics_dir` and `ledger` are one shared value produced by `_split_args` for
  every turn; `review_notes` and `note` vary by call site, and each prompt doc states its own value for them
