---
type: flow
slug: coder-dev
title: Coder development flow
---
# Coder development flow

- The `Dev` machine builds one story with a single owner turn. The turn plans the story, builds
  it, reviews it, fixes what the review finds and answers every finding. The flow then checks the
  turn with the plan record, the service gates, the answer file and a clean-tree test. It is
  entered by the Coder main flow or directly with `workhorse-coder run dev`. Implementation lives
  at `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev`.
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
- detail: [coder dev-story prompt](../formats/coder-dev-story-prompt.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_clean_pass_settles_the_fix_and_records_the_decline`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_red_gate_sends_its_output_back_and_a_green_turn_finishes`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_unanswered_finding_comes_back_named_in_the_report`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_blocked_turn_in_human_mode_parks_and_resumes_with_the_answer`
- tests: `workflows/tests/coder/dev/test_flow.py::test_checks_that_stay_red_past_the_lap_budget_park_instead_of_failing`
- tests: `workflows/tests/coder/dev/test_flow.py::test_work_the_turn_left_uncommitted_comes_back_named_in_the_report`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_path_dirty_before_the_story_began_is_not_the_story_s_to_commit`

The `docs` and `workspace` test fixtures stand up the inputs every dev-flow scenario runs
against. `docs` builds a docs repo carrying one epic and one authored story. `workspace` builds
two real git repos under a home config workspace naming them, since the gate walk and
the clean-tree check read both. They are documented at the
[coder dev package concept](../concepts/coder-dev-package.md).

The stages, in order: [setup](#setup), [own-the-story](#own-the-story), [checks](#checks), [operator-block](#operator-block), [finish](#finish).

The flow starts when the configured story slug resolves to a readable authored story; or when the workspace directories and story paths have been resolved before the owner turn.
It ends in one of these ways: a turn whose plan record, gates, answers and tree all pass finishes with the settled and declined finding ids; a turn that reports a block, or checks that stay red past the lap budget, waits for an operator; an epic-scoped operator answer leaves the flow as a replan outcome carrying the answer.

## Steps

### setup

- kind: prepare

The flow resolves the workspace directories and the story paths, then guards that the resolved
story file is readable. A missing story, an empty story slug, or an authored story with
incomplete sections is rejected before any agent turn.

### own-the-story

- kind: run
- detail: [coder dev-story prompt](../formats/coder-dev-story-prompt.md)

One high-power `dev-story` turn runs in the story's conversation with no timeout. It receives the
story identity, the spec directory, the worklist and answers file paths, a resume note read from
disk, the review prefix for this round, the open findings, the last gate report and the last
operator answer. The turn plans, builds, reviews, fixes and commits through its own subagents.
The flow stamps the spec files the turn wrote. Follow-ups the turn reports are filed in the work
list after the story, or in the backlog when the turn was itself a follow-up. Findings the review
reports are filed in the work list under the review prefix. A result of `blocked` goes to the
operator-block step.

### checks

- kind: verify

The flow records the plan structure from the turn's reply and commits the plan record. An invalid
plan record is the first failure. Otherwise the checks gather every failure of the turn. They
resolve the implementation context, move the code repositories to the run branch when one was
supplied, check the story status, and run each service's gates in `GATE_ORDER`, stopping at the
first dirty one. A status that already reads as finished is a failure. They then settle the open
findings against the answers file, and name any finding still open with the reason its answer was
rejected. They last list the paths the story changed and did not commit, minus the paths that were
dirty before the story began. With no failure the flow finishes. Otherwise the joined report goes
back to the owner turn as another repair lap. After `MAX_LAPS` laps the flow raises a block.

### operator-block

- kind: run

In `auto` mode a block goes first to the `resolve-operator` turn. The resolver may apply an answer
only when it can cite an existing decision, rule or acceptance criterion. In `human` or `operator`
mode, or once `MAX_BLOCKS` blocks have been spent, the flow awaits the operator on the story
`context.md`. The operator's answer is logged to the work log and re-enters the owner turn as its
authoritative context. An epic-scoped answer is handed back to the main flow for replanning.

### finish

- kind: run

The flow returns a `DevOutcome` listing the ids of the story's findings that were settled and the
ids that were declined.
