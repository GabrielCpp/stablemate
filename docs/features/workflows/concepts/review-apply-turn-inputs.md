---
type: concept
slug: review-apply-turn-inputs
title: Review apply turn inputs
---
# Review apply turn inputs

`Review.apply` supplies these three inputs together to one `apply-review` turn; they are not
alternative representations of the same value. The turn may modify only `story_path`, reads
and writes settlement material under `spec_dir`, and uses `review_notes` to identify the
implementation findings that remain to be resolved.

`story_path` and `spec_dir` therefore remain required on every review-application pass. An
empty `review_notes` is valid only when another apply state is carrying operator feedback as
the work instead. The settlement gate subsequently reads the sidecar from `spec_dir` rather
than trusting the turn's reported status.

- code: `workflows/src/workhorse_workflows/coder/review/flow.py::Review.apply`
- rule: provide `story_path`, `spec_dir`, and `review_notes` together; use empty `review_notes` only when operator feedback is the work
