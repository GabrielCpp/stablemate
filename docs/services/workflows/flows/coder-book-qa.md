---
type: flow
slug: coder-book-qa
title: Coder book QA flow
---
# Coder book QA flow

The `BookQa` machine judges one story by a run of the executable book of each service the story
touches. A service has an executable book when `services/<name>/service.py` exists under the repo
root. One seat turn brings those books up to the story's claims and names the calls the story
touches. The verdict then costs no model call: the flow checks each book and plays the named calls
against a copy of the stack that runs the story's code. The Coder main flow enters it first in
`qa`, before the [scenario QA flow](coder-qa.md), and `workhorse-coder run book_qa` enters it
directly. The seat replies with a [book QA owner result](../formats/book-qa-owner-result.md).

Inputs are the story slug, the epic, `operator_mode` (default `auto`), `target_env` (default
`local`) and the preexisting worktree snapshot. The flow ends in a `QaFlowResult` whose status is
`passed`, `refix` or `replan`. See the [QA schema contracts](../concepts/coder-qa-schema-contracts.md)
for that type and the [coder book qa package](../concepts/coder-book-qa-package.md) for the rules the
lane keeps.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- steps:
  - [run](../workhorse-coder.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder book qa package](../concepts/coder-book-qa-package.md)
- detail: [coder lane order](../concepts/coder-lane-order.md)
- detail: [coder main flow](coder-main.md)
- detail: [coder QA flow](coder-qa.md)
- detail: [book QA record](../formats/book-qa-record.md)
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_story_with_no_covered_service_passes_with_no_seat_and_no_stack`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_green_pass_plays_the_named_calls_records_them_and_lands_the_book`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_finding_beside_a_green_run_goes_back_to_the_developer_and_the_book_still_lands`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_findings_verdict_that_lists_no_finding_goes_back_to_the_seat`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_red_run_with_no_finding_goes_back_to_the_seat_with_the_output`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_red_check_goes_back_to_the_seat_before_any_play`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_run_that_stays_red_parks_at_the_operator_after_the_lap_budget`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_run_that_could_not_judge_asks_the_operator_and_spends_no_second_turn`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_stack_that_did_not_come_up_asks_the_operator_before_the_seat_starts`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_second_visit_replays_the_recorded_calls_with_no_seat`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_the_claims_the_seat_could_not_state_are_recorded_beside_its_calls`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_replay_keeps_the_recorded_unreached_claims`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_green_replay_over_a_recorded_finding_sends_it_back_again`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_red_replay_goes_to_the_seat_with_the_output_as_its_report`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_seat_that_names_no_call_for_a_covered_service_is_sent_back_before_any_play`
- tests: `workflows/tests/coder/book_qa/test_flow.py::test_a_product_edit_outside_the_book_is_refused_and_sent_back_unlanded`
- code: `workflows/src/workhorse_workflows/coder/book_qa/flow.py::BookQa` @5a49c22948b4

The seat session is keyed `book-qa:<story slug>`. The flow resets it on every ending except `refix`,
so the developer's fix returns to the same seat. Each ending releases the run's copy of the stack.
The stages, in order: [setup](#setup), [start](#start), [work](#work), [check](#check),
[operator-block](#operator-block).

The flow starts when the configured story slug resolves to a readable story path.
It ends in one of these ways: no service of the story has an executable book and the lane passes with
no agent call; every covered service's named calls play green with no finding and the lane passes;
they play green with findings and the lane ends as `refix`; the operator scopes an answer to the epic
and the lane ends as `replan`; the environment or the lap budget parks the run on the operator.

## Steps

### setup

- kind: prepare

`setup` resolves the slug to the story path, the spec directory and the story's services. A story
that does not resolve raises `WorkflowFailed` before any agent turn, because there is nothing to
judge.

### start

- kind: prepare

`start` lists the story's covered services. With none, the lane ends `passed` with no finding, no
stack and no agent turn, and the story's QA is the scenario lane alone. Otherwise it resolves the
implementation context with the repositories the story touched, names the run's lease on a copy of
the stack and brings the stack up. A stack that does not come up, with `ready` of `no` or `none`,
goes to the operator with the failed step and its notes. It never reaches the seat, because an
unhealthy environment is not a claim the developer can fix.

Then `start` reads `book-qa.json` from the spec directory. A record that holds services is a second
visit for the same story: the flow goes straight to `check` with the recorded calls and findings and
spends no seat turn. A story with no record goes to `work`. See the
[book QA record](../formats/book-qa-record.md).

### work

- kind: drive

`work` runs the `qa-book` seat at high power under the shared QA owner profile, with no wall-clock
bound and a silence limit. The turn reads the story, its plan and its review answers, then the diff.
It plays the calls its claims bear on before any edit to prove the base, brings each covered book up
to the story's claims and plays the calls again. It edits only under `services/<name>/`. It is
granted only the repositories the plan touches, and the stack's environment is scoped around the turn.
It reads no other QA's plan, report or evidence.

A `blocked` result goes to the operator block. A `findings` result that lists no finding goes back
to the seat as a lap, with a note to list each claim the app does not meet. Any other result
continues to `check` with the calls it named, the findings it listed and the claims it could not state in the book.

### check

- kind: verify

`check` works through the covered services in order. Nothing in it calls a model.

1. A covered service for which the seat named no call goes back to the seat as a lap, naming those
   services, before any play.
2. For each covered service the flow runs `ostler book check services.<name>`, which builds
   everything the book declares with no stack. A non-zero exit goes back to the seat as a lap with the
   tail of the output.
3. It then plays the service's named calls with `ostler book run services.<name> --only <calls>
   --copy <lease>`, writing its output under the spec directory's `qa/book` folder. Exit 3 means the
   environment could not be judged, and the flow asks the operator with the output and spends no
   lap. Any other non-zero exit goes back to the seat as a lap with the tail of the output.
4. When every service plays green the flow commits the changed paths under each covered book as one
   `test` commit that carries the story's footer. A product path the seat changed outside those folders
   refuses the commit, commits nothing and goes back to the seat as a lap that lists each path and says
   to restore it. A pass that left no uncommitted book path commits nothing.
5. It writes `book-qa.json` with the calls played, the findings the seat listed and the claims it
   could not state in the book, releases the stack
   copy, and ends. With findings the lane ends `refix`, and its result lists them with `qa` failed.
   With none it ends `passed`.

The record is what the [scenario QA flow](coder-qa.md) reads to leave out what the book judged. A
record with no finding makes the scenario lane defer the required obligations under the recorded
services' book pages, and the claims the seat listed as unreached stay the scenario lane's to cover.

A finding stops the story even on a green run, because a declared defect makes the run green by
design. A second visit enters this stage with the recorded calls, so a red replay goes to the seat
with the output as its report, and a green replay over a recorded finding ends `refix` again.

- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::covered_services` @5794657c4d83
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::book_check` @08d492ed6b13
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::book_run` @a32cf444c3c3
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::commit_service_book` @c3c45d5dacbc
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::read_book_record` @d7c92c6f59ff
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::write_book_record` @509765d04b59
- code: `workflows/src/workhorse_workflows/coder/book_qa/nodes.py::defer_book_judged` @986fdb2642e7

### operator-block

- kind: drive

A repair lap is spent each time `check` sends failures back, up to `MAX_LAPS`. At the cap, or on a
blocked seat result, the flow takes the block path with the notes. The `resolve` turn runs in `auto`
mode and answers from what is already written down. In a human operator mode, or once `MAX_BLOCKS`
blocks are spent, the flow writes the block to the story context file and returns `Await`, and a
spent lap budget is a question to the operator and never a give-up. `read_operator` logs the answer
and resumes `work` with it. An answer scoped to the epic resets the session, releases the stack copy
and ends the flow with `replan`. An environment fault found in `start` or by exit 3 asks the operator
without a resolver turn.
