---
type: flow
slug: review-debt
title: Review the debt register
---
# Review the debt register

- A maintainer runs `workhorse-review-debt run` to see which records on the
  [debt register](../../ostler/concepts/the-debt-register.md) share a cause. The `ReviewDebt`
  machine reads every record, has one agent turn group them, and refuses a report that leaves a
  record out, names one twice or names one the register does not hold. A report that passes is
  written to `<artifacts>/backlog/trends.md`. Each cluster with at least `decision_threshold`
  records not yet bound to a decision gets one proposed
  [decision record](../../ostler/concepts/decision-records.md).
- Implementation lives at `workflows/src/workhorse_workflows/review_debt/flow.py::ReviewDebt`.
- The read holds records of every status in every repository. A closed record stays in the read,
  because a dropped record whose cause recurs is part of a trend.
- A `record.md` that does not parse is logged and left out of the read's ids. The report is not
  asked to name it, so the accounting passes without it.
- `max_sendbacks` defaults to 2 and caps the send-backs. At most three grouping turns run.
- `decision_threshold` defaults to 3.
- fixture: none, because the dry run reads a stand-in register and writes nothing the check reads
- steps:
  - [run](../workhorse-review-debt.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-review-debt.dot")
- end: the dry run reads an empty register and ends with a zero exit status
- verify: exit_status(code=0)
- detail: [review-debt package](../concepts/review-debt-package.md)
- detail: [trend report](../formats/trend-report.md)
- detail: [debt register trends file](../formats/debt-trends-file.md)
- tests: `workflows/tests/review_debt/test_flow.py::test_a_complete_report_writes_trends_naming_every_id`
- tests: `workflows/tests/review_debt/test_flow.py::test_the_first_turn_is_given_the_listing_and_no_feedback`
- tests: `workflows/tests/review_debt/test_flow.py::test_a_report_missing_an_id_is_sent_back_naming_it`
- tests: `workflows/tests/review_debt/test_flow.py::test_three_bad_reports_fail_the_run_with_the_gap_and_write_nothing`
- tests: `workflows/tests/review_debt/test_flow.py::test_duplicated_and_unknown_ids_are_named_in_the_feedback`
- tests: `workflows/tests/review_debt/test_flow.py::test_an_empty_register_ends_without_a_turn_or_a_file`
- tests: `workflows/tests/review_debt/test_decisions.py::test_a_cluster_of_three_is_drafted_and_a_cluster_of_two_is_left`
- tests: `workflows/tests/review_debt/test_decisions.py::test_a_second_run_over_the_same_register_and_report_proposes_nothing`
- tests: `workflows/tests/review_debt/test_decisions.py::test_a_refusal_from_propose_ends_the_run_naming_it`

The stages, in order: [read](#read), [group-and-account](#group-and-account), [write-trends](#write-trends), [plan-decisions](#plan-decisions), [draft-and-file](#draft-and-file).

The flow starts when the register holds at least one readable record.
It ends in one of these ways: an empty register returns `Done` with the reason "register is empty", with no agent turn and no `trends.md`; a report that still fails accounting after the last send-back raises `WorkflowFailed` naming the wrong ids and writes nothing; a passing report with no cluster at the threshold writes `trends.md` and returns `Done` with an empty `Proposed`; a passing report writes `trends.md`, proposes one decision per cluster at the threshold and returns `Done` with a `Proposed` naming each decision id; a decision ostler refuses raises `WorkflowFailed` naming the refusal.

## Steps

### read

- kind: prepare

`start` calls `read_register`, which reads every parseable record on the register with its id and
one listing line. The listing line carries the id, repository, area, status, pattern and summary,
separated by tabs. A read with no ids ends the run as `Done` with the reason "register is empty".

### group-and-account

- kind: run
- detail: [trend report](../formats/trend-report.md)

`group` renders `review-register.md` with the listing lines, the register path and a feedback
block that is empty on the first turn. The turn returns a `TrendReport`. `account` compares the
ids the report names with the ids of the read. It names the ids the report leaves out, the ids it
names more than once, and the ids the register does not hold. A report with all three empty
passes. A failing report goes back to the same turn with every wrong id named in the feedback
block. After `max_sendbacks` send-backs the next failing report raises `WorkflowFailed`, whose
reason lists the wrong ids by kind, and the run writes no file.

### write-trends

- kind: run
- detail: [debt register trends file](../formats/debt-trends-file.md)

`write_trends` renders the passing report over the read into `trends.md` at the register's root
and commits that one file in the artifacts repository as `chore: review the debt register`. The
rendering depends only on the report and the read, so a resumed run that renders the same text
commits nothing.

### plan-decisions

- kind: verify

`plan_decisions` calls `select_candidates`. It re-reads the register, narrows each cluster to its
records with no `decision`, and keeps the clusters whose narrowed records reach
`decision_threshold`. With none kept, the run returns `Done` with an empty `Proposed`.

### draft-and-file

- kind: run

`draft` takes the candidates one at a time. `narrow_candidate` re-reads the register first and
drops the records a decision has bound since the plan. A candidate still at the threshold gets one
`draft-decision.md` turn, which receives the cluster name, its cause, its listing lines and the
register path, and returns a `DecisionDraft`. `file_decision` passes the draft and the cluster's
ids to ostler's decision proposal. Ostler writes one decision at `status: proposed`, binds each
evidence record to it, and leaves each record open, all in one artifacts commit. A candidate that
fell below the threshold is skipped without a turn. A refusal raises `WorkflowFailed` naming
ostler's message. A rerun over the same register and report proposes nothing, because its
clusters' records are bound already.
