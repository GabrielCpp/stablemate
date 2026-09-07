---
type: concept
slug: failure-classification-views
title: Failure classification documentation views
---
# Failure classification documentation views

[`classify_turn`](../../../../workhorse/workhorse/runner/failure.py) is the single implementation
that turns a completed backend turn into its result or a typed failure. These two concepts are
complementary views of that implementation, not alternatives a caller can select between.

Read [classify_turn](classify-turn.md) for the function's complete input, output, branch-order, and
session-persistence contract. Read [Agent turn failure classification](failure-classification.md)
when the surrounding error types and marker helpers are also relevant. The source does not
supersede either view: `classify_turn` is the shared classifier, while the same module also declares
the errors and predicates documented by the broader concept.

- rule: use `classify_turn` for the classifier function's contract; use Agent turn failure classification for the module-wide failure model. Neither view supersedes the other.
