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
and its package boundary is the [Author main package](../concepts/author-main-package.md). The
workflow fields select the dispatch mode and carry the mode-specific inputs: `mode` defaults to
`epic`, `epic`, `bullet`, `layers`, and `services` support one story seed, `rubric` and `survey_dir`
support a survey, `baseline_inventory` and `parity_survey_dir` support a parity survey, and
`operator_mode` defaults to `auto`.

- start: the default run has `mode=epic` and the repository contains one `docs/roadmaps/*.md` file with `type: roadmap` and `status: approved`.
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
- detail: [Author main intake](../concepts/author-main-intake.md)
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

## Invocations

### plan-and-dispatch
- on: [author roadmap intake](#plan-and-dispatch)
- trigger: after setup and after each completed or blocked stage
- when: the approved roadmap and its current planning artifacts are available
- verify: count(subject="planner invocations with current artifacts", equals=1)
- does:
  - validates that exactly one milestone owns only the approved roadmap
  - verify: count(subject="sole-source roadmap milestones", equals=1)
  - returns `kind: milestone` when that milestone is missing or not sole-source
  - verify: json_path(path="$.kind", equals="milestone")
  - returns `kind: epic-split` when the milestone epics are absent, duplicated, unknown, or not in a valid ordered split
  - verify: json_path(path="$.kind", equals="epic-split")
  - returns `kind: epic-author` for the first milestone-ordered epic missing its document or researched seeds
  - verify: json_path(path="$.kind", equals="epic-author")
  - returns `kind: story-split` for the first milestone-ordered epic whose local story graph or semantic split receipt is invalid
  - verify: json_path(path="$.kind", equals="story-split")
  - returns `kind: story-author` for the first unblocked story in epic and dependency-DAG order whose audit receipt is missing or stale
  - verify: json_path(path="$.kind", equals="story-author")
  - returns `kind: finalize` when every ordered epic has a current valid story graph and no story remains to author
  - verify: json_path(path="$.kind", equals="finalize")
- code: `workflows/src/workhorse_workflows/author/main/nodes/planner.py::plan_author_step`
- detail: [artifact-derived author stage selection](../concepts/artifact-derived-author-stage-selection.md)
- tests: `workflows/tests/author/test_planner.py::test_story_author_uses_story_dag_order_and_author_current`
- tests: `workflows/tests/author/test_planner.py::test_blocked_story_is_skipped_for_the_remainder_of_one_main_run`

## Phase Details

### Setup
The machine resolves the repository root and configured document paths. In epic mode it requires
one approved roadmap and carries its resolved path in the run context; it does not substitute the
backlog or create a feature inventory.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.setup`
- code: `workflows/src/workhorse_workflows/author/main/nodes/config.py::load_config`

### Plan and dispatch
After setup, the planner rereads the approved roadmap's planning graph and selects one incomplete
stage. The machine hands off to milestone creation, epic splitting, [epic authoring](../concepts/author-epic-author-subflow.md), story splitting,
story authoring, or finalization, then returns to planning so each stage is selected from the
artifacts currently on disk. Epic documentation and researched seeds for every queued epic are
completed before story splitting begins. For a `story-split` stage, the dispatcher hands the
selected epic and operator mode to the [story-split subflow](../concepts/story-split-subflow.md);
that subflow creates the epic's story topology, converges mechanical and semantic coverage, and
returns a digest-bound acceptance receipt before planning resumes. Epic authoring receives the
selected epic and operator mode, and returns its evidence before the planner selects the next
stage. A blocked story is recorded in the planner's skip set while the flat queue continues to
other stories; an unblocked story is handed off with its epic, story, run-directory feedback path,
and operator mode.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start`
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.next_stage`
- code: `workflows/src/workhorse_workflows/author/main/nodes/planner.py::plan_author_step`
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow`

`Author.next_stage` passes the planner's selected epic and story into the matching subflow. A
blocked `StoryAuthor` result is not terminal: it is logged, its `epic/story` key is added to the
current run's blocked set, and planning resumes with that key skipped. Any other stage result
returns to the same planner with the existing blocked set. When the planner returns `finalize`,
the dispatcher hands off `Finalize` and does not plan another stage.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.next_stage`
- tests: `workflows/tests/author/test_planner.py::test_blocked_story_is_skipped_for_the_remainder_of_one_main_run`

The same dispatcher has two explicit non-epic branches. `mode=survey` hands off to `Surveyor` with
the rubric and survey directory and stops after discovery. `mode=parity-survey` hands off to
`ParitySurveyor` with its baseline inventory and survey directory and stops after that discovery.
`mode=story` adopts the backlog through the shared `adopt_backlog` node before seeding one bullet
in an existing epic, hands off to `StoryAuthor`, and prunes the consumed backlog bullet without
running the epic planning or commit tail. Adoption resolves the consuming repository from
`repo_dir`, assigns ids to unnamed backlog bullets through Ostler, logs the successful result,
and raises `WorkflowFailed` with Ostler's message when adoption fails; the story seed is not
attempted after that failure.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start`
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::adopt_backlog`
- tests: workflows/tests/author/test_workflow.py::test_story_mode_authors_one_bullet_and_does_not_commit
- tests: workflows/tests/author/test_workflow.py::test_survey_mode_runs_the_surveyor_and_stops_at_discovery

The story branch hands `epic`, `bullet`, `layers`, and `services` to `seed_story`, then hands the
returned story slug and the current run directory to `StoryAuthor`. It prunes the source backlog
bullet only after the handoff is prepared. The survey branches return `Done` immediately after
their handoff, while epic mode returns `Continue` into `next_stage`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start`

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
