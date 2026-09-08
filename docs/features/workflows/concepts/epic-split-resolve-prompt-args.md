---
type: concept
slug: epic-split-resolve-prompt-args
title: Epic split resolve prompt args
---
# Epic split resolve prompt args

`EpicSplit.resolve` in `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
is the one assembly site for the six template arguments rendered into the resolve-epic-split.md
prompt: `roadmap`, `milestone`, `epics_dir`, `review_notes`, `context_path`, and `block_notes`. It
calls `self._split_args()` with no argument for the first four — so `review_notes` always renders
as the empty string on this turn — then layers `context_path` (from `self._context_path()`) and
`block_notes` (the accumulated notes explaining why review/rework could not converge) on top.

This is not a competition between implementations: all six `field` nodes on
[author resolve-epic-split prompt](../author-resolve-epic-split-prompt.md) that cite
`EpicSplit.resolve` as their `code:` are documenting distinct members of the one payload this
method assembles for a single prompt call, not alternative ways of producing the same value. No
ranking exists among them — a consumer reads each field for its own named role, and none is a
substitute for another. `roadmap`, `milestone`, and `epics_dir` are the same immutable context
fields also shared with [epic split prompt args](epic-split-prompt-args.md); `review_notes` is
fixed empty on this turn only; `context_path` and `block_notes` exist solely to drive the
operator-resolution turn.

- code: `workflows/src/workhorse_workflows/author/epic_split/flow.py::EpicSplit.resolve`
- rule: read `roadmap`, `milestone`, and `epics_dir` for the immutable split context, `review_notes`
  as always empty on this turn, `context_path` for where the operator record lives, and
  `block_notes` for why the prior cycle blocked; do not substitute or rank fields
- detail: [epic split resolve documentation scope](epic-split-resolve-documentation-scope.md)
