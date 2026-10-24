---
type: concept
slug: review-debt-package
title: Review-debt package
---
# Review-debt package

The `review_debt` package is the `review-debt` workflow. Its nodes read the
[debt register](../../ostler/concepts/the-debt-register.md), account a
[trend report](../formats/trend-report.md) against that read, write the
[trends file](../formats/debt-trends-file.md), and propose
[decision records](../../ostler/concepts/decision-records.md). The
[review-debt flow](../flows/review-debt.md) orders them. The package resolves the register through
ostler from the ambient `repo_dir` and spells no register path of its own.

- code: `workflows/src/workhorse_workflows/review_debt/flow.py::ReviewDebt` @1be6aeba806f
- code: `workflows/src/workhorse_workflows/review_debt/workflow.py` @69cce66c2aa2
- detail: [workhorse-review-debt command](../workhorse-review-debt.md)

## Methods

### read_register

- sig: `read_register(logger, repo_dir: str = "") -> CompleteRead`
- does: reads every parseable record of every status in every repository of the register
- verify: count(subject="records of every status in the read", equals=1)
- does: logs each `record.md` that does not parse and returns it under `unreadable`, outside the ids
- verify: count(subject="unreadable records outside the ids", equals=1)
- does: returns an empty read under `--dry-run`
- verify: json_path(path="$.ids", equals="[]")
- returns: the ids of the read, their listing lines and the register path
- verify: json_path(path="$.ids[0]", equals="api-cart")
- code: `workflows/src/workhorse_workflows/review_debt/nodes/read.py::read_register` @f3bb0f59d614
- tests: `workflows/tests/review_debt/test_nodes.py::test_the_read_holds_every_status_in_every_repository`
- tests: `workflows/tests/review_debt/test_nodes.py::test_an_unreadable_record_is_carried_and_never_accounted`
- tests: `workflows/tests/review_debt/test_nodes.py::test_an_empty_shelf_reads_as_no_ids`
- tests: `workflows/tests/review_debt/test_nodes.py::test_a_dry_run_read_is_empty`

### account

- sig: `account(logger, read_ids: list[str], report: TrendReport) -> Accounting`
- does: returns as `missing` the read ids the report does not name, in the order of the read
- verify: json_path(path="$.missing[0]", equals="X-2")
- does: returns as `duplicated` the read ids the report names more than once, inside one cluster or across a cluster and a singleton
- verify: json_path(path="$.duplicated[0]", equals="X-1")
- does: returns as `unknown` the ids the report names that the read does not hold
- verify: json_path(path="$.unknown[0]", equals="X-9")
- returns: an `Accounting` that is `ok` when all three lists are empty
- verify: count(subject="accounting gaps", equals=0)
- code: `workflows/src/workhorse_workflows/review_debt/nodes/accounting.py::account` @27241ea05276
- tests: `workflows/tests/review_debt/test_account.py::test_an_exact_cover_is_ok`
- tests: `workflows/tests/review_debt/test_account.py::test_a_missing_id_is_named`
- tests: `workflows/tests/review_debt/test_account.py::test_a_duplicated_id_is_named_across_a_cluster_and_a_singleton`
- tests: `workflows/tests/review_debt/test_account.py::test_an_id_twice_in_one_cluster_is_duplicated`
- tests: `workflows/tests/review_debt/test_account.py::test_an_unknown_id_is_named`

### write_trends

- sig: `write_trends(logger, read: CompleteRead, report: TrendReport, repo_dir: str = "") -> TrendsWritten`
- does: writes the rendered report to `trends.md` at the register root and commits that file in the artifacts repository as `chore: review the debt register`
- verify: contents(subject="trends.md", matches="(?m)^# Debt register trends$")
- returns: the written path and whether the write made a commit, which is false when the text did not change
- verify: json_path(path="$.committed", equals=false)
- code: `workflows/src/workhorse_workflows/review_debt/nodes/trends.py::write_trends` @82e8ad7ad1cc
- tests: `workflows/tests/review_debt/test_nodes.py::test_writing_the_same_report_twice_commits_once`

### select_candidates

- sig: `select_candidates(logger, report: TrendReport, threshold: int, repo_dir: str = "") -> Candidates`
- does: narrows each cluster to its records on the register with no `decision`, with their listing lines
- verify: count(subject="bound records left out of a candidate", equals=0)
- returns: the narrowed clusters that hold at least `threshold` records
- verify: count(subject="$.clusters", equals=1)
- code: `workflows/src/workhorse_workflows/review_debt/nodes/decisions.py::select_candidates` @bf8c2226857e
- tests: `workflows/tests/review_debt/test_decisions.py::test_select_candidates_keeps_only_unbound_ids_at_the_threshold`
- tests: `workflows/tests/review_debt/test_decisions.py::test_a_lower_threshold_drafts_the_smaller_cluster_too`

### narrow_candidate

- sig: `narrow_candidate(logger, candidate: Candidate, repo_dir: str = "") -> Candidate`
- does: re-reads the register and drops the candidate's records that a decision has bound since it was selected, logging how many it dropped
- verify: count(subject="records bound since the plan", equals=0)
- code: `workflows/src/workhorse_workflows/review_debt/nodes/decisions.py::narrow_candidate` @bf8c2226857e
- tests: `workflows/tests/review_debt/test_decisions.py::test_bound_records_drop_out_of_a_larger_cluster`

### file_decision

- sig: `file_decision(logger, candidate: Candidate, draft: DecisionDraft, repo_dir: str = "") -> Filed`
- does: proposes one decision through ostler from the draft's title, context, decision and consequences
- verify: json_path(path="$.ok", equals=true)
- does: cites the candidate's ids as the decision's evidence
- verify: count(subject="candidate ids bound to the decision", equals=3)
- returns: the new decision id, or `ok` false with ostler's refusal message
- verify: json_path(path="$.message", matches="already bound to decision")
- code: `workflows/src/workhorse_workflows/review_debt/nodes/decisions.py::file_decision` @bf8c2226857e
- tests: `workflows/tests/review_debt/test_decisions.py::test_the_draft_turn_is_given_the_cluster_and_the_shelf`
- tests: `workflows/tests/review_debt/test_decisions.py::test_a_refusal_from_propose_ends_the_run_naming_it`

### gap

- sig: `gap(accounting: Accounting) -> str`
- returns: the wrong ids joined by kind, as `missing from the report: ...`, `listed more than once: ...` and `not on the register: ...`, each part present only when it has ids
- verify: json_path(path="$.gap", matches="^missing from the report: ")
- code: `workflows/src/workhorse_workflows/review_debt/flow.py::gap` @1be6aeba806f
- tests: `workflows/tests/review_debt/test_flow.py::test_duplicated_and_unknown_ids_are_named_in_the_feedback`
