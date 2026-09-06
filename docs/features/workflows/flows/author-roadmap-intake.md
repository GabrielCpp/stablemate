---
type: flow
slug: author-roadmap-intake
title: Author roadmap intake
---
# Author roadmap intake

The [workhorse-author run command](../workhorse-author.md#run) starts the Author machine, which
turns one approved release contract into exactly one milestone of ordered epics and vertical
stories. The roadmap remains durable; Author never copies it into or prunes it as a mutable
worklist. Its composition root is the [author workflow composition root](../concepts/author-workflow-composition-root.md),
and its package boundary is the [Author main package](../concepts/author-main-package.md).

- start: the default run has `mode=epic` and the caller names one `docs/roadmaps/*.md` file with `type: roadmap` and `status: approved`.
- steps:
  - [setup](#setup)
  - [plan and dispatch](#plan-and-dispatch)
  - [finalize](#finalize)
- end: the authored roadmap is the durable source of exactly one milestone whose ordered epics and
  stories are ready for Coder.
- verify: count(subject="roadmap-owned milestones", equals=1)
- verify: persists(subject="the authored roadmap and its planning graph")
- detail: [author workflow composition root](../concepts/author-workflow-composition-root.md)
- detail: [Author main package](../concepts/author-main-package.md)
- detail: [author finalize subflow](../concepts/author-finalize-subflow.md)
- tests: workflows/tests/author/test_workflow.py::test_epic_mode_authors_one_roadmap_milestone_and_commits_it
- tests: workflows/tests/author/test_config.py::test_roadmap_must_source_exactly_one_nonempty_milestone
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.setup`
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start`
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.next_stage`
- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`
- code: `workflows/src/workhorse_workflows/author/main/nodes/planner.py::plan_author_step`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::validate_roadmap_milestone`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::mark_roadmap_authored`

## Phase Details

### Setup
The machine resolves the repository root and configured document paths. In epic mode it requires
one approved roadmap and carries its resolved path in the run context; it does not substitute the
backlog or create a feature inventory.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.setup`
- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`

### Plan and dispatch
After setup, the planner rereads the approved roadmap's planning graph and selects one incomplete
stage. The machine hands off to milestone creation, epic splitting, epic authoring, story splitting,
story authoring, or finalization, then returns to planning so each stage is selected from the
artifacts currently on disk. Epic documentation and researched seeds for every queued epic are
completed before story splitting begins. A blocked story is recorded in the planner's skip set while
the flat queue continues to other stories; an unblocked story is handed off with its epic, story,
run-directory feedback path, and operator mode.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start`
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.next_stage`
- code: `workflows/src/workhorse_workflows/author/main/nodes/planner.py::plan_author_step`

The same dispatcher has two explicit non-epic branches. `mode=survey` hands off to `Surveyor` with
the rubric and survey directory and stops after discovery. `mode=parity-survey` hands off to
`ParitySurveyor` with its baseline inventory and survey directory and stops after that discovery.
`mode=story` adopts the backlog, seeds one bullet in an existing epic, hands off to `StoryAuthor`,
and prunes the consumed backlog bullet without running the epic planning or commit tail.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start`
- tests: workflows/tests/author/test_workflow.py::test_story_mode_authors_one_bullet_and_does_not_commit
- tests: workflows/tests/author/test_workflow.py::test_survey_mode_runs_the_surveyor_and_stops_at_discovery

### Finalize
Finalization verifies reconciliation, whole-graph integrity, and the roadmap-owned milestone. It
validates the authored artifacts again, advances the roadmap from `approved` to `authored` without
rewriting its body, and commits the authored planning documents. A failed final validation commits
an incomplete marker instead of reporting a successful run.

The [author finalize subflow](../concepts/author-finalize-subflow.md) runs these gates in order. A
reconciliation or integrity failure is first offered to an automatic resolver up to its bounded
resolution count; human mode, exhausted resolution, or an escalated resolver response reaches the
operator context file. Only passing or explicitly skipped gates proceed to the next validation.

- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.close`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::validate_roadmap_milestone`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::mark_roadmap_authored`
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::validate_artifacts`
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::verify_integrity`
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::verify_reconcile`
- code: `workflows/src/workhorse_workflows/author/main/nodes/artifacts.py::commit_author`

When a story handoff returns an audit block, the dispatcher keeps the result, logs the blocked
epic/story pair, adds that pair to the in-run skip set, and selects another stage. When the planner
reports no remaining stage, the dispatcher hands off to `Finalize` and ends after its result.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.next_stage`
- tests: workflows/tests/author/test_planner.py::test_blocked_story_is_skipped_for_the_remainder_of_one_main_run
