---
type: flow
slug: coder-dev
title: Coder development flow
---
# Coder development flow

- The `Dev` machine builds one story in three owner turns on one conversation: a plan turn, a
  build turn and a review turn. The flow then checks the review turn with the plan record, the
  clone check, the service gates, the answer file and a clean-tree test, and sends each failure back to the review
  phase. It is entered by the Coder main flow or directly with `workhorse-coder run dev`.
  Implementation lives at `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev`.
- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-coder.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder dev package](../concepts/coder-dev-package.md)
- detail: [coder main flow](coder-main.md)
- detail: [coder dev phase turns](../concepts/coder-dev-phase-turns.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_clean_pass_settles_the_fix_and_records_the_decline`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_red_gate_sends_its_output_back_and_a_green_turn_finishes`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_unanswered_finding_comes_back_named_in_the_report`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_blocked_turn_in_human_mode_parks_and_resumes_with_the_answer`
- tests: `workflows/tests/coder/dev/test_flow.py::test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing`
- tests: `workflows/tests/coder/dev/test_flow.py::test_work_the_turn_left_uncommitted_comes_back_named_in_the_report`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_path_dirty_before_the_story_began_is_not_the_story_s_to_commit`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_fresh_story_runs_plan_build_and_review_in_that_order`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_failed_check_reenters_review_and_not_build`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_operator_answer_on_a_build_block_returns_to_build`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_departure_without_advice_sends_the_build_back_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_without_an_advisor_a_departure_passes_and_every_phase_runs_at_max`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_a_consult_on_file_stays_declined`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_conversation_other_than_the_briefed_one_opens_with_the_full_brief_again`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_copy_the_story_added_comes_back_as_a_copies_failure_before_any_service_gate`
- detail: [coder lap clone check](../concepts/coder-lap-clone-check.md)

The `docs` and `workspace` test fixtures stand up the inputs every dev-flow scenario runs
against. `docs` builds a docs repo carrying one epic and one authored story. `workspace` builds
two real git repos under a home config workspace naming them, since the gate walk and
the clean-tree check read both. They are documented at the
[coder dev package concept](../concepts/coder-dev-package.md).

The stages, in order: [setup](#setup), [plan](#plan), [build](#build), [review](#review), [checks](#checks), [operator-block](#operator-block), [finish](#finish).

The flow starts when the configured story slug resolves to a readable authored story; or when the workspace directories and story paths have been resolved before the plan turn.
It ends in one of these ways: a review turn whose plan record, gates, answers and tree all pass finishes with the settled and declined finding ids; a turn that reports a block, or a lap budget spent, waits for an operator; an epic-scoped operator answer leaves the flow as a replan outcome carrying the answer.

## Steps

### setup

- kind: prepare

The flow resolves the workspace directories and the story paths, then guards that the resolved
story file is readable. A missing story, an empty story slug, or an authored story with
incomplete sections is rejected before any agent turn.

### plan

- kind: run
- detail: [coder dev-plan prompt](../formats/coder-dev-plan-prompt.md)
- detail: [coder dev phase turns](../concepts/coder-dev-phase-turns.md)

The flow forgets which conversation each phase was briefed on, so each phase opens with its full
brief. A story QA has sent back skips this step and the build, and starts at the review. One
`max`-power plan turn runs in the story's conversation with no timeout. It receives the story
identity, the spec directory, the worklist path, the path its brief is kept at, a resume note read
from disk, the declared services, and the last operator answer. It writes and commits the plan
files and no product code. The flow writes the rendered brief to disk before the turn, and records
the conversation id the turn ran on. A result of `blocked` goes to the operator-block step.
Otherwise the build step runs.

### build

- kind: run
- detail: [coder dev-build prompt](../formats/coder-dev-build-prompt.md)

One build turn runs on the same conversation. It runs on the `high` power tier when the turn is
offered an `advisor` delegate, and on `max` otherwise. It reads the plan, builds it, walks the
criteria, and commits. It reports every departure from the plan with the advisor's answer. A
low-power judge reads each follow-up the turn reports, and the flow logs every one it reads as no
product work. The rest are filed as `coder` records on the
[debt register](../../ostler/concepts/the-debt-register.md), each with its area and pattern,
through the [coder backlog contract](../concepts/coder-backlog-contract.md). No coder lane drains
them. A result of `blocked` goes to the operator-block step. When an advisor is offered and a
departure carries no advice, the flow sends the build back with a report naming each such
departure. After `MAX_LAPS` such laps the flow raises a block. Otherwise the review step runs.

### review

- kind: run
- detail: [coder dev-review prompt](../formats/coder-dev-review-prompt.md)
- detail: [coder dev follow-up prompt](../formats/coder-dev-follow-up-prompt.md)

One review turn runs on the same conversation, on the same power rule as the build. It receives
the answer file path, the review prefix for this round, the findings QA filed, the other open
findings, and the last check report. It has a fresh reviewer judge the diff, triages and fixes the
findings, and answers each one. When an advisor is offered, it consults the advisor before each
decline and reports the consult. A repair lap on the conversation this phase last ran on gets the
follow-up note instead of the brief. The note names the brief's path and carries the report, the
findings and the operator answer. The flow stamps the spec files the turn wrote, files the
follow-ups as the build step does, files the findings the review reports in the work list under
the review prefix, and records the consults. A result of `blocked` goes to the operator-block step.

### checks

- kind: verify

The flow records the plan structure from the turn's reply and commits the plan record. An invalid
plan record is the first failure. Otherwise the checks gather every failure of the turn. They
resolve the implementation context, move the code repositories to the run branch when one was
supplied, and check the story status. A status that already reads as finished is a failure.
They then run the [lap clone check](../concepts/coder-lap-clone-check.md) on the code
repositories the plan dispatches into, so a copy the story added of existing code fails the lap
before any gate runs. They last run each service's gates in `GATE_ORDER`, stopping at the first
dirty one. They then settle the open
findings against the answers file, and name any finding still open with the reason its answer was
rejected. A declined finding of the `Reuse` category holds only as a coincidence that names two
different reasons the copies change. They last list the paths the story changed and did not commit, minus the paths that were
dirty before the story began. With no failure the flow finishes. Otherwise the joined report goes
back to the review phase as another repair lap. When an advisor is offered, the settlement also
reopens each declined finding with no consult on file, and the report names it. After `MAX_LAPS`
laps the flow raises a block.

- code: `workflows/src/workhorse_workflows/coder/shared/owner.py::MAX_LAPS` @46bbdfd84d88

Before the checks run again on a later lap, a self-check reruns the scenarios the last scored QA
run did not pass against a leased stack copy, so a regression the owner turn introduced surfaces
before QA spends a turn on it.

- code: `workflows/src/workhorse_workflows/coder/shared/failed.py::last_failed_scenarios` @0c28ea7dc660

The checks also walk the story's acceptance criteria against the plan's own `## Acceptance Walk`
section, naming any criterion the plan's walk does not cover; a follow-up, which carries no
acceptance criteria of its own, skips this check. When the plan holds more than one section of
that title, the walk reads the shallowest one, so a follow-up section's own walk never stands in
for the plan's.

- code: `workflows/src/workhorse_workflows/coder/shared/walk.py::acceptance_walk` @c36ec782d6b4
- code: `workflows/src/workhorse_workflows/coder/shared/walk.py::criteria_count` @c36ec782d6b4
- code: `workflows/src/workhorse_workflows/coder/shared/walk.py::walked` @c36ec782d6b4

### operator-block

- kind: run

In `auto` mode a block goes first to the `resolve-operator` turn. The resolver may apply an answer
only when it can cite an existing decision, rule or acceptance criterion. In `human` or `operator`
mode, or once `MAX_BLOCKS` blocks have been spent, the flow awaits the operator on the story
`context.md`. The operator's answer is logged to the work log and re-enters the phase that raised
the block as its authoritative context. An epic-scoped answer is handed back to the main flow for replanning.

### finish

- kind: run

The flow returns a `DevOutcome` listing the ids of the story's findings that were settled and the
ids that were declined.
