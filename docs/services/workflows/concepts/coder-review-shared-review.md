---
type: concept
slug: coder-review-shared-review
title: Coder review shared nodes
---
# Coder review shared nodes

The shared review module supplies the deterministic work around the dev owner's review: where the
review turns read, whether a fix's cited evidence holds up, whether a "not a defect" decline names
its test, whether a Reuse decline names a coincidence, the settlement of filed findings, and the non-blocking operator feedback the QA check
polls. It treats the settlement ledger and the evidence the owner cites, not the owner's claimed
status, as the authority for whether a finding is settled.

- code: `workflows/src/workhorse_workflows/coder/shared/review.py::__all__` @ba6796cad3b9
- detail: [coder review context](../formats/review-context.md)
- detail: [coder review feedback](../formats/review-feedback.md)
- detail: [settlement](../formats/settlement.md)

## Methods

### resolve_review_context

- sig: `resolve_review_context(logger, spec_dir="", repo="", repo_dir="", workspace="") -> ReviewContext`
- does: resolves the documentation repository from `repo_dir`, or the artifacts dir while a workspace is active
- verify: json_path(path="$.docs_repo_path", equals="docs/stories/acme-story/story.md")
- does: loads `plan-context.json` from the resolved story spec directory when `spec_dir` is non-empty
- verify: count(subject="review plan-context reads", equals=1)
- does: resolves workspace repository records from the named `workspace`, falling back to `repo_dir` as a single repository
- verify: count(subject="review workspace resolutions", equals=1)
- does: selects the explicitly named `repo` as the affected set when no plan context exists
- verify: json_path(path="$.affected_repo_paths", equals="example affected repo paths")
- does: otherwise selects the deduplicated repositories named by plan services
- returns: a `ReviewContext` whose `docs_repo_path` is the judging working directory
- returns: a `ReviewContext` whose `affected_repo_paths` contains the selected code repository paths
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::resolve_review_context` @ba6796cad3b9

### evidence_gap

- sig: `evidence_gap(answer: dict, repos: list[str], changed: dict[str, list[str]]) -> str`
- does: names the first cited commit that exists in none of the story's code repositories
- verify: json_path(path="$", matches="^commit [0-9a-f]+ is in none of the story's code repos$")
- does: names the first cited path that is not among the files the story changed
- verify: json_path(path="$", matches="^path .+ is not among the files this story changed in its code repos$")
- does: names the first cited test that appears in no file the story changed
- verify: json_path(path="$", matches="^test .+ appears in no file this story changed$")
- returns: an empty string when every citation holds
- verify: json_path(path="$", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::evidence_gap` @ba6796cad3b9

### decline_gap

- sig: `decline_gap(answer: dict, repos: list[str]) -> str`
- does: treats a declined answer whose reason opens with "not a defect", in any case, as a "not a defect" decline
- does: names the missing test when a "not a defect" decline cites no `- test:` bullet
- verify: json_path(path="$", matches="^a \"not a defect\" decline cites no test: ")
- does: names the first cited test that appears in no tracked file of the story's code repositories
- verify: json_path(path="$", matches="^test .+ appears in no tracked file of the story's code repos$")
- returns: an empty string for a decline of any other kind, or a "not a defect" decline whose tests all exist
- verify: json_path(path="$", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::decline_gap` @ba6796cad3b9
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_not_a_defect_decline_with_no_test_comes_back_open`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_not_a_defect_decline_naming_a_test_no_repo_holds_comes_back_open`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_decline_of_another_kind_settles_without_a_test`

### coincidence_gap

- sig: `coincidence_gap(answer: dict) -> str`
- does: accepts a reason that opens with "coincidence:", in any case and under leading markdown
- verify: count(subject="coincidence prefixes read through leading markdown", equals=1)
- does: requires at least two different reasons after the prefix, separated by `;`
- verify: json_path(path="$", matches="give two different reasons the copies change")
- returns: the instruction to decline only as a coincidence or to extract the repeated code, for any other reason
- verify: json_path(path="$", matches="^a Reuse finding is declined only as a coincidence: ")
- returns: an empty string when the coincidence names two different reasons
- verify: json_path(path="$", equals="")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::coincidence_gap` @ba6796cad3b9
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_reuse_decline_without_a_coincidence_comes_back_open_with_the_coincidence_text`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_reuse_decline_without_two_different_reasons_comes_back_open`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_the_coincidence_prefix_may_wear_markdown_and_any_case`

### settle_findings

- sig: `settle_findings(logger, story_slug="", story_id="", filed=None, repos=None, repo_dir="", reuse=None) -> Settlement`
- does: settles the filed finding ids against the dev owner's answer list through Ostler, keyed on `story_id` rather than `story_slug`, and writes the settlement ledger
- verify: persists(subject="the review settlement ledger")
- does: commits the ledger as a `docs` commit when it lies inside the documentation repository
- verify: count(subject="review settlement commits", equals=1)
- does: moves a fixed answer to `rejected` with its evidence gap when its cited evidence does not hold
- verify: json_path(path="$.rejected", equals="{}")
- does: moves a declined answer to `rejected` with its decline gap when it is a "not a defect" decline without an existing test
- verify: json_path(path="$.declined", equals="[]")
- does: checks a declined answer whose id is in `reuse` with its coincidence gap instead of its decline gap
- does: lists a finding as open when the ledger leaves it open or its answer is rejected
- verify: json_path(path="$.open", equals="[]")
- raises: `WorkflowFailed` when `story_id` is empty
- returns: a `Settlement` of the settled, declined, open and rejected findings with the ledger's errors
- verify: json_path(path="$.settled", equals="[]")
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::settle_findings` @ba6796cad3b9
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_reuse_decline_naming_two_different_reasons_settles_as_declined`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_not_a_defect_decline_of_a_finding_that_is_not_reuse_still_follows_the_decline_rule`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_not_a_defect_decline_with_no_test_comes_back_open`
- tests: `workflows/tests/coder/shared/test_review_settlement.py::test_a_not_a_defect_decline_citing_a_tracked_test_settles_as_declined`

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
- code: `workflows/src/workhorse_workflows/coder/shared/review.py::check_feedback` @ba6796cad3b9
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_dropped_operator_note_buys_exactly_one_re_qa`
