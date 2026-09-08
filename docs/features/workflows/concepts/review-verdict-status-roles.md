---
type: concept
slug: review-verdict-status-roles
title: Review verdict status roles
---
# Review verdict status roles

- code: `workflows/src/workhorse_workflows/coder/shared/schemas/review.py::ReviewVerdict.status`
- rule: use the review verdict format to learn the status value's routing contract; use the review-implementation prompt format to learn the binding review decision that produces it

`ReviewVerdict.status` is one required `ReviewStatus` value, produced by the holistic reviewer.
The schema defines `approved` when no Critical or Major finding remains, `needs_changes` when a
fix is required, and `blocked` when the missing decision or evidence is outside the repository.

Both field nodes are current views of that same value, not alternative implementations. The
review verdict format is the canonical reply contract and records how each value routes the
workflow. The review-implementation prompt format records the decision rule supplied to the
reviewer: approval has no remaining Critical or Major finding, required changes have at least
one, and a block is external. Read the view matching the question; neither replaces the other.
