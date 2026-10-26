---
type: flow
slug: coder-main
title: Coder main flow
---
# Coder main flow

- The default [Coder composition root](../concepts/coder-workflow-composition-root.md) runs this
  machine when no specialist flow is selected. It hands implementation, documentation, QA,
  backlog fixing and CI repair to the specialist flows while retaining the worklist and
  transition decisions here. Its agent turns use the [coder conversation lifecycle](../concepts/coder-conversation.md),
  [prompt role resolution](../concepts/coder-prompt-role-resolution.md), and [rendered schema contracts](../concepts/coder-render-schema-contracts.md).

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- steps:
  - [run](../workhorse-coder.md#run)
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-coder.dot")
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)

The implementation is `workflows/src/workhorse_workflows/coder/main/flow.py::Coder`, whose nodes
register against the one blueprint every Coder flow shares.

- code: `workflows/src/workhorse_workflows/coder/shared/blueprint.py::blueprint` @0cbd22929b3f
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder main package](../concepts/coder-main-package.md)
- detail: [coder workflow composition root](../concepts/coder-workflow-composition-root.md)
- detail: [coder main PR boundary](../concepts/coder-main-pr-boundary.md)
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`
- tests: `workflows/tests/coder/test_workflow.py::test_a_pr_run_lands_every_item_on_one_branch_and_opens_no_pr_offline`
- tests: `workflows/tests/coder/test_workflow.py::test_a_commit_run_stays_on_the_current_branch_and_names_each_story`
- tests: `workflows/tests/coder/test_workflow.py::test_a_finished_epic_is_pruned_from_the_queue_in_its_own_commit`
- tests: `workflows/tests/coder/test_workflow.py::test_an_opened_pr_goes_to_the_ship_lane_for_ci_and_stays_open`
- tests: `workflows/tests/coder/test_workflow.py::test_a_required_final_docs_block_replans_in_either_mode`

The stages, in order: [initialize](#initialize), [route](#route), [story-pipeline](#story-pipeline), [agent-turn-contract](#agent-turn-contract), [backlog-drain](#backlog-drain), [story-commit](#story-commit), [delivery](#delivery).

The flow starts when the run has a resolvable repository context and names one story, one epic, or every epic in the queue; or when the run's `delivery` parameter is `pr` or `commit`, and defaults to `pr`.
It ends in one of these ways: a commit run has worked the whole worklist and left one commit per item on the branch it started on, each naming its story; a pr run has worked the whole worklist on one run branch, opened its pull requests, and left them open with CI green for a reviewer to merge; a blocked documentation, CI or dirty-worktree condition is checkpointed at an operator gate instead of being silently committed or skipped.

## Steps

### initialize

- kind: prepare

`setup` resolves the workspace directories before any item is worked, so the replan path has the
same repository context as story work. `start` clears the previous run's worklist and answer log,
then files every story the launch names onto the worklist, in order. A pr run then cuts one
`feat/` run branch off the current branch, named for the story, the epic, or the run. A commit run
cuts nothing and stays on the current branch.

### route

- kind: run

`route` first consolidates follow-ups that share a cause and hands finished work's open findings to
the follow-up that owns their cause, filing one when none does. It then claims the next story or
follow-up off the worklist. The worklist decides how many items the run works before it stops: one
run is not one story, and not one pull request per story. An empty worklist ends a commit run
after tearing down the QA stack, and sends a pr run to delivery.

- code: `workflows/src/workhorse_workflows/coder/shared/causes.py::consolidate` @93617ea77353
- code: `workflows/src/workhorse_workflows/coder/shared/causes.py::own` @93617ea77353
- code: `workflows/src/workhorse_workflows/coder/shared/judge.py::Judge` @eb6949952f8c
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/judge.py::Ruling` @6d06f2f4b655

`consolidate` and `own` read and rewrite the worklist's follow-up and finding items through the
shared `work` module: the kinds, statuses and payload fields a follow-up or finding carries, and
the helpers that file, find, replace and merge them.

- code: `workflows/src/workhorse_workflows/coder/shared/work.py::FOLLOW_UP` @d1b341a8165d
- code: `workflows/src/workhorse_workflows/coder/shared/work.py::open_findings` @d1b341a8165d
- code: `workflows/src/workhorse_workflows/coder/shared/work.py::follow_up_items` @d1b341a8165d
- code: `workflows/src/workhorse_workflows/coder/shared/work.py::findings_of` @d1b341a8165d
- code: `workflows/src/workhorse_workflows/coder/shared/work.py::find` @d1b341a8165d
- code: `workflows/src/workhorse_workflows/coder/shared/work.py::file` @d1b341a8165d
- code: `workflows/src/workhorse_workflows/coder/shared/work.py::replace` @d1b341a8165d

### story-pipeline

- kind: run

Each claimed item is snapshotted against pre-existing work, resolved to its story's paths, and
sent through `dev`, `document` and `qa`. A pr run hands `dev` the run branch to land on. A commit
run hands it none. QA findings are filed against the item and return to its dev owner. A replan
from the dev owner, QA or documentation rewrites the epic and re-files its open stories.

### agent-turn-contract

- kind: drive
- detail: [coder replan-epic prompt](../formats/coder-replan-epic-prompt.md)

The main flow hands implementation, documentation, QA and backlog work to typed sub-flows. Their
turns receive the story-derived backbone or a lane-specific session according to the specialist
flow's contract. The main flow preserves returned statuses rather than reconstructing their
conversations. Its one own turn is `replan`, which uses the authoritative operator answer and
`ReplanResult` at high power.

### backlog-drain

- kind: run

A passing QA result hands off to the [`fix` flow](coder-fix.md). That flow drains the open `qa`
records of the workspace on the [debt register](../../ostler/concepts/the-debt-register.md). It
documents and commits each drained item and closes its record before this machine resumes. The
current story's documentation-recheck flag is carried forward unchanged.

### story-commit

- kind: run

`finalize` re-runs documentation only when QA or the drain marked the story for a recheck.
`commit` reads every repository. Paths still uncommitted go back to the item's dev owner. A clean
reading stamps a story passed, and `standing` marks the item done. Every commit carries the
story's `Story:` footer, in both modes. When an epic run has nothing of its epic left, `standing`
prunes the epic from the queue in a commit of its own.

### delivery

- kind: run

Only a pr run reaches delivery. `deliver` opens one pull request per repository the run branch
changed, listing the stories it delivered. With no pull request opened, the run tears down QA and
ends. Otherwise `ship` hands the branch to the `fix_ci` flow with no merge base, so it waits for CI
and repairs it, and leaves the merge to a reviewer.
