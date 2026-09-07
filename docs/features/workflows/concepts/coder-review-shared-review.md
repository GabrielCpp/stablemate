---
type: concept
slug: coder-review-shared-review
title: Coder review shared nodes
---
# Coder review shared nodes

The shared review module supplies deterministic setup, cycle cleanup, settlement verification, and
non-blocking operator feedback. It resolves review inputs once, passes the resolved context to
review turns, and treats the settlement ledger rather than an apply turn's claimed status as the
authority for whether findings are complete.

- code: `workflows/src/workhorse_workflows/coder/shared/review.py::__all__`
- detail: [coder review flow](../flows/coder-review.md)
- detail: [coder review context](../review-context.md)
- detail: [coder review feedback](../review-feedback.md)
- detail: [coder implementation result](../impl-result.md)

## Methods

### resolve_review_context

- sig: `resolve_review_context(logger, spec_dir="", repo="", docs_path="", repo_dir="", workspace_file="") -> ReviewContext`
- does: resolves the documentation repository from `docs_path` and `repo_dir`
- verify: json_path(path="$.docs_repo_path", matches=".+")
- does: loads `plan-context.json` from the resolved story spec directory when `spec_dir` is non-empty
- verify: count(subject="review plan-context reads", equals=1)
- does: resolves workspace repository records from `workspace_file`, falling back to `repo_dir` as a single repository
- verify: count(subject="review workspace resolutions", equals=1)
- does: selects the explicitly named `repo` as the affected set when no plan context exists
- verify: json_path(path="$.affected_repo_paths", matches=".+")
- does: otherwise selects the deduplicated repositories named by plan services
- verify: json_path(path="$.affected_repo_paths", matches=".+")
- returns: a `ReviewContext` whose `docs_repo_path` is the judging working directory
- verify: json_path(path="$.docs_repo_path", matches=".+")
- returns: a `ReviewContext` whose `affected_repo_paths` contains the selected code repository paths
- verify: json_path(path="$.affected_repo_paths", matches=".+")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::resolve_review_context`
- tests: `workflows/tests/coder/review/test_flow.py::test_an_approved_review_stamps_the_specs_and_stops`
- tests: `workflows/tests/coder/review/test_flow.py::test_an_explicit_repo_is_the_whole_affected_set`

### clear_review_resolution

- sig: `clear_review_resolution(logger, spec_dir="", story_slug="") -> ImplResult`
- does: returns an applied result without deleting files when `story_slug` is empty
- verify: json_path(path="$.status", equals="applied")
- does: deletes the current cycle's `review-resolution.json` when it exists under `spec_dir`
- verify: removed(subject="the stale review-resolution.json sidecar")
- does: deletes the current cycle's `review-settlement.json` when it exists under `spec_dir`
- verify: removed(subject="the stale review-settlement.json sidecar")
- returns: an applied `ImplResult` whose notes list the sidecar filenames that were cleared
- verify: json_path(path="$.status", equals="applied")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::clear_review_resolution`
- tests: `workflows/tests/coder/review/test_flow.py::test_a_previous_cycles_settlement_cannot_settle_this_ones_findings`

### verify_review_resolution

- sig: `verify_review_resolution(logger, spec_dir="", docs_path="", story_slug="", repo_dir="") -> ImplResult`
- does: returns `needs_changes` when `story_slug` is empty or `review-resolution.json` is absent
- verify: json_path(path="$.status", equals="needs_changes")
- does: runs Ostler settlement verification against the story's resolution sidecar and writes the settlement ledger
- verify: persists(subject="the review settlement ledger")
- does: returns `needs_changes` when Ostler reports a settlement error
- verify: json_path(path="$.status", equals="needs_changes")
- does: returns `needs_changes` when the settlement ledger cannot be read after settlement
- verify: json_path(path="$.status", equals="needs_changes")
- does: returns `blocked` when the settlement ledger reports an unresolvable finding
- verify: json_path(path="$.status", equals="blocked")
- does: returns `applied` when every finding in the settlement ledger is verified
- verify: json_path(path="$.status", equals="applied")
- does: returns `needs_changes` when any finding remains open or its proof is missing or wrong
- verify: json_path(path="$.status", equals="needs_changes")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::verify_review_resolution`
- tests: `workflows/tests/coder/review/test_flow.py::test_the_settlement_gate_overrules_an_unproven_applied_claim`
- tests: `workflows/tests/coder/review/test_flow.py::test_a_story_with_no_verdict_sidecar_is_re_applied_not_believed`
- tests: `workflows/tests/coder/review/test_flow.py::test_a_blocked_settlement_escalates_without_spending_the_budget`

### check_feedback

- sig: `check_feedback(logger, run_dir="") -> Feedback`
- does: polls the run-scoped inbox for its oldest outstanding message
- verify: count(subject="outstanding feedback messages consumed", equals=1)
- does: replies to a found message so the same note is not returned by a later poll
- verify: count(subject="replies to consumed feedback messages", equals=1)
- does: returns an empty `Feedback` when no outstanding message exists
- verify: json_path(path="$.present", equals=false)
- does: returns present `Feedback` containing the message body when a note exists
- verify: json_path(path="$.present", equals=true)
- returns: a `Feedback` with only `present` and `content` fields, without the inbox message scope
- verify: json_path(path="$.scope", absent=true)
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::check_feedback`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_dropped_operator_note_buys_exactly_one_re_qa`
