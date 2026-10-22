---
type: flow
slug: coder-qa
title: Coder QA flow
---
# Coder QA flow

The `Qa` machine hands one story's QA to a single owner session, then reruns and gates what the
owner claims. The owner plans, runs, audits and repairs through its own subagents. The flow
rebuilds the context packet and the stack, reruns the plan the owner left, and decides whether
the story passes, goes back to the dev owner with findings, or replans. The Coder main flow
enters it after documentation passes, and `workhorse-coder run qa` enters it directly.

Inputs are the story slug, optional docs and workspace selectors, the epic, `operator_mode`
(default `auto`), `target_env` (default `local`), `stop_at_first_verdict` and the preexisting
worktree snapshot. The owner turn replies with a [QA owner result](../formats/qa-owner-result.md).
The flow ends in a `QaFlowResult` whose status is `passed`, `refix` or `replan`. See the
[QA schema contracts](../concepts/coder-qa-schema-contracts.md) for those types.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-coder.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder qa package](../concepts/coder-qa-package.md)
- detail: [coder main flow](coder-main.md)
- detail: [coder QA subflow](../concepts/coder-qa-subflow.md)
- tests: `workflows/tests/coder/qa/test_flow.py::test_one_clean_pass_spends_one_owner_turn`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_failed_run_with_findings_sends_them_back_as_a_refix`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_blocked_owner_is_answered_and_resumes_with_the_answer`
- tests: `workflows/tests/coder/qa/test_flow.py::test_an_epic_scoped_answer_hands_the_story_back_to_replan`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_dev_target_reports_findings_instead_of_refixing`
- tests: `workflows/tests/coder/qa/test_flow.py::test_a_run_killed_mid_repair_resumes_on_the_owner_turn_with_its_report`

`target_env=local` sends product findings back to the dev owner as a `refix`. `target_env=dev`
reports the findings and passes, so the tracker carries them. `stop_at_first_verdict` finishes
a green run in one turn and reports the first red run without a repair turn, while a stack
fault is still the owner's to repair. The owner session is keyed `qa:<story slug>`. The flow
resets it on every ending except `refix`, so the dev owner's fix returns to the same QA session.
Each ending releases the run's copy of the stack, and `docs_recheck_required` is true only when
the owner moved the code.

The flow is implemented by `workflows/src/workhorse_workflows/coder/qa/flow.py::Qa`.

The stages, in order: [setup](#setup), [start](#start), [work](#work), [check](#check), [operator-block](#operator-block).

The flow starts when the configured story slug resolves to a readable story path; or when the previous run's QA evidence is cleared and the OKF context packet and stack are checked.
It ends in one of these ways: the plan passes and clears every gate; the scored run fails on the product with findings; the operator scopes an answer to the epic; a development target reports its findings and passes; a block parks on the operator when laps or blocks are spent.

## Steps

### setup

- kind: prepare

`setup` resolves the slug to the story path, the spec directory and the `qa/` directory. A story
that does not resolve raises `WorkflowFailed` before any agent turn, because there is nothing to
QA.

### start

- kind: prepare

`start` snapshots the code state, clears the previous run's QA evidence, and resolves the
implementation context with the repositories the story touched. When the workspace file and the
story id are both set, it also resolves story-source provenance and fails the run when the
sources are invalid. It then detects the OKF book, names the run's lease on a copy of the stack,
and records the stack target. The preflight builds and validates the OKF context packet and
brings the stack up. Each failure becomes a line of the first owner turn's report instead of an
abort, because a broken packet or stack is the owner's to repair.

### work

- kind: drive

`work` runs the `qa-story` owner turn at high power under the shared owner profile, with no
wall-clock bound and a silence limit. The turn reads the story, the spec directory, the
verification setup, the fixtures, the QA run plan, the QA tool catalog and the last report. It is
granted only the repositories the plan touches. It also learns whether a standing `qa_plan.py`
already lints and validates, so it adopts that plan rather than authoring a new one. The stack's
environment is scoped around the turn. Specs are stamped after the turn. A `blocked` result goes
to the block path. Any other result continues to `check` with its findings and the scenarios it
claims it dry-ran.

### check

- kind: verify

`check` rebuilds the preflight, then lints the plan, validates it against the packet, and
verifies that every claimed scenario dry-ran green. Any failure spends a lap and returns to `work`
with the failure as the report. A clean preflight runs the plan once through `run_qa_plan`, files
the backlog items the run wrote, and stamps the specs.

A failed run with findings, or any failed run under `stop_at_first_verdict`, ends the flow. A
failed run with no finding goes back to the owner with its failing scenarios and a note that the
failure is unclassified. A run that did not finish goes back as unfinished. Findings beside a
passing run go back as unproved.

A passed run must also clear four gates before the story is believed. The evidence gate checks
the runner's artifacts. The operator feedback inbox is read, and a note goes back to the owner.
Declared regression suites run, and a suite that is neither passed nor skipped goes back. The
sentinel ids are checked after the screenshots are flushed. Under `stop_at_first_verdict`, a
passing run that fails a gate finishes as a `refix` with a fallback finding.

### operator-block

- kind: drive

A repair lap is spent each time `check` sends failures back, up to `MAX_LAPS`. At the cap, or
on a blocked owner result, the flow takes the block path with the notes. The `resolve` turn runs
in `auto` mode and answers from what is already written down. In a human operator mode, or
once `MAX_BLOCKS` blocks are spent, the flow writes the block to the story context file and
returns `Await`. `read_operator` logs the answer and resumes `work` with it. An answer scoped to
the epic resets the session, releases the stack copy and ends the flow with `replan`.
