---
type: flow
slug: coder-dev
title: Coder development flow
---
# Coder development flow

- The `Dev` machine plans one story, validates the plan's service paths, dispatches each planned
  service layer, and repairs implementation changes against the layer's declared gates. It is
  entered by the Coder main flow or directly with `workhorse-coder run dev`. Implementation lives
  at `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev`.

- start: the configured story slug resolves to a readable authored story
- verify: exit_status(code=0)
- start: the workspace directories and story paths have been resolved before the planning turn
- verify: count(subject="resolved development inputs", equals=1)
- steps:
  - [setup](#setup)
  - [plan](#plan)
  - [path-validation](#path-validation)
  - [replan-with-answer](#replan-with-answer)
  - [dispatch](#dispatch)
  - [layer-selection](#layer-selection)
  - [implementation](#implementation)
  - [gates](#gates)
  - [repair](#repair)
  - [operator-resolution](#operator-resolution)
- end: every service layer in the approved plan has passed its story-status and declared service gates
- verify: exit_status(code=0)
- end: an epic-scoped operator answer leaves the development flow with the answer for queue-level replanning
- verify: count(subject="epic-scoped development replans", equals=1)
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder dev package](../concepts/coder-dev-package.md)
- detail: [coder main flow](coder-main.md)
- detail: [coder development nodes](../concepts/coder-dev-nodes.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_plans_stamps_branches_and_implements_every_layer`
- tests: `workflows/tests/coder/dev/test_an_epic_scoped_answer_leaves_the_flow_to_be_replanned`

The `docs` and `workspace` test fixtures stand up the inputs every dev-flow scenario runs
against: `docs` builds a docs repo carrying one epic and one authored story so the story-slot
resolution has something real to look up, and `workspace` builds two real git repos under a
checked-in `.code-workspace` file naming them, since `branch_code_repos` checks out a branch in
each and the per-layer-gate dispatch walks both. They are documented at the
[coder dev package concept](../concepts/coder-dev-package.md).

`setup` resolves workspace directories and the story slug, rejects an unauthored or unreadable
story before any agent turn, and returns the shared `StoryPaths` context. It also establishes the
story conversation identity used by later turns.

Implementation and repair routing is delegated to the [development nodes](../concepts/coder-dev-nodes.md):
plan and implementation blocks preserve resolver evidence, repair laps are bounded per layer,
and an exhausted budget awaits an operator rather than producing a failed or apparently
successful run.

## Steps

### setup

- kind: prepare

The flow calls workspace and story path preparation, then guards that the resolved story file is
readable. A missing story, an empty story slug, or an authored story with incomplete sections is
rejected before planning begins.

### plan

- kind: run
- detail: [coder plan-story prompt](../coder-plan-story-prompt.md)

The high-power `plan-story` turn receives the story, epic, spec directory, workspace markers, and
story-derived conversation. It snapshots code worktrees first, writes the plan artifacts in the
docs repository, stamps those plan files as typed specs, and routes a blocked result to the plan
operator gate. Plan mutations in code repositories are removed while pre-existing dirt is kept.

### path-validation

- kind: verify

The recorded plan is projected and checked against the workspace. A valid or silent validator
result advances to dispatch. An invalid service or plan-file path receives at most three low-power
path-repair turns; an unresolved result then enters the plan operator gate. A successful repair
resets the repair conversation before validation resumes.

### replan-with-answer

- kind: run
- detail: [coder replan-with-answer prompt](../coder-replan-with-answer-prompt.md)

A plan blocked at the validation gate receives an operator answer from the story context. The
`replan-with-answer` turn re-plans the story around the operator's decision, using a fresh
conversation scoped to the `block-repair` worklist. If the re-plan is still blocked, the revised
plan re-enters the validation gate. If the re-plan succeeds, the repair conversation is reset and
validation resumes with the revised plan.

### dispatch

- kind: run

The approved plan is read back, implementation context is resolved for the target environment,
and every code repository named by the plan is moved to the story branch. The dispatch list keeps
the plan's declared implementation order.

### layer-selection

- kind: run

The cursor selects the next unimplemented service layer from the recorded plan. When no layer
remains, the flow returns a ready `DevResult`; otherwise it passes the selected layer and cursor to
implementation.

### implementation

- kind: run
- detail: [coder implement-plan prompt](../coder-implement-plan-prompt.md)

Each selected layer starts a fresh story implementation conversation on the first entry, spends a
session turn, and runs one high-power `implement-plan` turn with the layer plan, service path and
type, verification setup, QA run plan, declared gates, and any operator answer. A blocked result is
sent to the implementation operator gate rather than being treated as an empty successful layer.

### gates

- kind: verify

The story status is checked before service gates on every lap; a status that says the story is
finished before QA becomes a repair finding. Otherwise the flow runs the service's configured gates
in `GATE_ORDER` and stops at the first dirty result. Skipped or silent gates do not fail the layer.
The clean result advances the cursor to the next layer.

### repair

- kind: run
- detail: [coder dev-fix prompt](../coder-dev-fix-prompt.md)

A dirty status or gate is converted into a `FailureReport`. While the shared three-lap repair
budget remains, a `dev-fix` turn receives the report, changed files, service identity, and story
trailers, then the flow reruns the gates. Repeated report digests raise the turn power; an exhausted
budget enters the implementation operator gate rather than ending the run.

### operator-resolution

- kind: run

In `auto` mode, a resolver may apply an answer only when it can cite an existing decision, rule, or
acceptance criterion; otherwise the flow awaits the operator on the story `context.md`. `human` and
`operator` modes skip the resolver and wait directly. A story-scoped answer re-enters planning or
the current implementation layer with the answer and consumes the context; an epic-scoped answer
returns `DevResult(status="replan")` to the queue. Resolver turns are capped at three per gate,
but the underlying block is never abandoned.

## Invocations

### repair-plan-paths

- on: [path-validation step](#path-validation)
- trigger: invalid service path or plan-file path in validated plan structure
- does:
  - corrects repository path, service path, implementation order, or plan-file values
- does:
  - leaves plan design and narrative text unchanged
- does:
  - returns full replacement `PlanResult` structure
- consumes: [coder-repair-plan-paths-prompt](../coder-repair-plan-paths-prompt.md)
- status: returns `PlanResult` with status `rework` when paths are corrected and re-validated
- verify: json_path(path="$.status", equals="rework")
- errors: workflow failure if validator continues to reject paths after correction
- verify: exit_status(code=1)
- code: `workflows/src/workhorse_workflows/coder/dev/nodes.py::refine`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_unresolvable_service_path_reworks_the_plan`
- tests:

