---
type: flow
slug: coder-main
title: Coder main flow
---
# Coder main flow

- The default [Coder composition root](../concepts/coder-workflow-composition-root.md) runs this
  machine when no specialist flow is selected. It hands implementation, review, documentation,
  QA, backlog fixing, CI repair, and merge work to the specialist flows while retaining the queue
  and transition decisions here. Its agent turns use the [coder conversation lifecycle](../concepts/coder-conversation.md),
  [prompt role resolution](../concepts/coder-prompt-role-resolution.md), and [rendered schema contracts](../concepts/coder-render-schema-contracts.md).

- start: the run has a resolvable repository context and its checkpointed mode is `epic` or `story`
- verify: exit_status(code=0)
- start: a story-mode run has a non-empty story slug, or epic mode can inspect the configured epic queue
- verify: count(subject="coder run entry paths", equals=1)
- steps:
  - [initialize](#initialize)
   - [epic-queue](#epic-queue)
   - [story-pipeline](#story-pipeline)
   - [agent-turn-contract](#agent-turn-contract)
  - [backlog-drain](#backlog-drain)
  - [story-commit](#story-commit)
  - [pull-request-gates](#pull-request-gates)
- end: story mode has committed the selected story and finished its story pull request, or epic mode has advanced through the queue and completed each eligible epic pull request
- verify: count(subject="coder terminal paths", equals=1)
- end: a blocked documentation, CI, merge, or dirty-worktree condition is checkpointed at an operator gate instead of being silently committed or skipped
- verify: count(subject="coder operator-gated blocking paths", equals=1)

The implementation is `workflows/src/workhorse_workflows/coder/main/flow.py::Coder`.
- detail: [coder handoff boundary contract](../concepts/coder-handoff-boundary.md)
- detail: [coder main package](../concepts/coder-main-package.md)
- detail: [coder workflow composition root](../concepts/coder-workflow-composition-root.md)
- detail: [coder main PR boundary](../concepts/coder-main-pr-boundary.md)
- tests: `workflows/tests/coder/test_workflow.py::test_one_epic_of_one_story_builds_it_prunes_the_queue_and_ends_on_an_empty_queue`
- tests: `workflows/tests/coder/test_workflow.py::test_the_pr_cluster_passes_through_offline_and_still_advances_the_queue`
- tests: `workflows/tests/coder/test_workflow.py::test_story_mode_cuts_its_own_branch_and_ends_at_its_own_pr`
- tests: `workflows/tests/coder/test_workflow.py::test_a_required_final_docs_block_parks_for_an_operator_in_either_mode`

## Steps

### initialize

- kind: prepare

`setup` resolves the workspace directories before any story is selected, so the planning-only
replan and merge paths have the same repository context as story work. `start` records the run,
then either branches the explicit story or initializes the base branch for epic queue processing.

### epic-queue

- kind: run

Epic mode selects the front epic, branches every repository for it, and repeatedly selects the next
unimplemented story. An empty epic queue tears down the reusable QA stack and ends normally. A
blocked epic is flagged and set aside so the next epic can be considered; a completed epic proceeds
to pull-request preparation.

### story-pipeline

- kind: run

Each selected story is snapshotted against pre-existing work, resolved to its paths, and sent through
`dev`, `review`, `document`, and `qa`. A development or QA rescope/rework returns to the appropriate
pipeline state with its counters preserved. Documentation failure parks at the documentation
operator gate. QA failure in the development environment documents the attempt and terminates
without a commit; other exhausted QA paths remain operator-gated inside QA.

The story's epic is resolved from the prepared story when story mode was handed a bare slug,
otherwise from the queue selection or the explicit epic parameter.

### agent-turn-contract

- kind: drive
- detail: [coder replan-epic prompt](../coder-replan-epic-prompt.md)
- detail: [coder settle-worktree prompt](../coder-settle-worktree-prompt.md)
- detail: [coder fix-merge prompt](../coder-fix-merge-prompt.md)

The main flow hands story implementation, review, documentation, QA, and backlog work to typed
sub-flows. Their turns receive the story-derived backbone or a lane-specific session according to
the specialist flow's contract; the main flow preserves returned statuses and counters rather than
reconstructing their conversations. The main flow's own turns are bounded and typed: `replan` uses
the authoritative operator answer and `ReplanResult` at high power, `settle` uses the story's
implementation conversation and `WorktreeSettled`, and `fix_merge` uses a separate epic merge
conversation and `MergeFixResult` at high power.

### backlog-drain

- kind: run

A passing QA result hands the backlog to the `fix` flow. That flow documents and commits each
drained item before this machine resumes, while the current story's documentation-taint flag is
carried forward unchanged.

### story-commit

- kind: run

The finalization state re-runs documentation only when QA or backlog mutation marked the story
tainted. Epic mode checks the repositories, allows one chained settle turn for uncommitted work,
stamps the story only after a clean reading, and returns to story selection. Story mode commits the
selected story, tears down QA, and opens its story pull request. A second unchanged dirty reading
parks at the dirty-worktree operator gate.

The settle turn is chained to the story's implementation conversation, but `commit` reads the
worktree again before stamping the story.

### pull-request-gates

- kind: run

After an epic's queue is pruned, its pull request is opened when the branch is independently
shippable. A branch carrying unmerged work from a set-aside epic is left without a PR so that the
earlier gate cannot be bypassed.
CI passes or is unavailable before merge; failed CI receives at most three automated repair laps
before a human CI gate. Merge conflicts receive at most two automated resolution laps before a
human merge gate. A successful or unavailable merge returns to epic selection, and a resumed run
recognizes an already merged PR before deciding it is unavailable.
