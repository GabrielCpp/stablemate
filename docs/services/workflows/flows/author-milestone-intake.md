---
type: flow
slug: author-milestone-intake
title: Author milestone intake
---
# Author milestone intake

The [workhorse-author run command](../workhorse-author.md#run) starts the Author machine, which
turns one approved milestone into ordered epics and vertical stories. The milestone folder
remains durable; Author reads it and never copies it into or prunes it as a mutable worklist. Its composition root is the [author workflow composition root](../concepts/author-workflow-composition-root.md),
and its package boundary is the [Author main package](../concepts/author-main-package.md). The
workflow fields select the dispatch mode and carry the mode-specific inputs: `mode` defaults to
`epic`, `epic`, `record`, `layers`, and `services` support one story seed, `rubric` and `survey_dir`
support a survey, `baseline_inventory` and `parity_survey_dir` support a parity survey, and
`operator_mode` defaults to `auto`.

- fixture: none, because the walk dry-runs the registered flow, which stands in for every agent turn
- start: the working directory holds no rendered graph
- verify: absent(subject="workhorse-author.dot")
- steps:
  - [run](../workhorse-author.md#run)
- end: the dry run leaves the command with a zero exit status
- verify: exit_status(code=0)
- detail: [author workflow composition root](../concepts/author-workflow-composition-root.md)
- detail: [Author main package](../concepts/author-main-package.md)
- detail: [Author main intake](../concepts/author-main-intake.md)
- detail: [author finalize subflow](../concepts/author-finalize-subflow.md)
- tests: workflows/tests/author/test_workflow.py::test_epic_mode_authors_the_approved_milestone_and_commits_it
- tests: workflows/tests/author/test_config.py::test_epic_authoring_selects_the_approved_milestone_folder
- tests: workflows/tests/author/test_config.py::test_epic_authoring_fails_on_a_readiness_error_and_lists_it

The machine itself is implemented by `Author`. Configuration, work-list filling, the completion
gate, and milestone validation are implemented by `load_config`, `fill_work`, `check_completion`,
`validate_milestone_epics`, and `mark_milestone_authored`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::load_config` @1e565a154642
- code: `workflows/src/workhorse_workflows/author/main/nodes/fill.py::fill_work` @0a6247ab8773
- code: `workflows/src/workhorse_workflows/author/main/nodes/completion.py::snapshot_epics` @becb105386f9 @0
- code: `workflows/src/workhorse_workflows/author/main/nodes/completion.py::check_completion` @becb105386f9
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::validate_milestone_epics` @cbdf7f3f88f8
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::mark_milestone_authored` @cbdf7f3f88f8

The stages, in order: [setup](#setup), [fill and drain](#fill-and-drain), [completion gate](#completion-gate), [finalize](#finalize).

The flow starts when the default run has `mode=epic` and the repository contains exactly one `docs/milestones/<slug>/milestone.md` with `status: approved` and no readiness finding.
It ends in one of these ways: the approved milestone becomes `authored`, and its ordered epics and stories are ready for Coder.

## Phase Details

### Setup
The machine resolves the repository root and configured document paths. In epic mode it selects
the one approved milestone folder through Ostler and runs its readiness check. Any error finding
fails the run before a turn, and the finding list is the failure message. It carries the
milestone's resolved path in the run context and does not substitute the debt register or create a
feature inventory.

Setup is implemented by `Author.setup` and `load_config`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.setup` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/shared/nodes/config.py::load_config` @1e565a154642

### Fill and drain
In epic mode the machine records a digest of the milestone body, then runs the stages as drains
over the run's work list. It hands off to epic splitting only while the milestone lists no valid
ordered epics. A fill state files the next kind from the ostler graph, and a drain state hands each
pending item to its stage and settles the item when the stage returns. Epics run first, as
[epic authoring](../concepts/author-epic-author-subflow.md) for each epic in milestone order.
Story splitting follows for every epic, through the [story-split subflow](../concepts/story-split-subflow.md),
which creates the epic's story topology, converges mechanical and semantic coverage, and returns a
digest-bound acceptance receipt. Story authoring comes last, in epic order and story DAG order. A
story is handed off with its epic, story, run-directory feedback path, operator mode, and the
operator's note when the item was requeued. Each authoring prompt shows that note under an
"Operator answer" heading.

Filling and draining are implemented by `Author.start`, `Author.epics`, `Author.story_splits`,
`Author.stories`, `fill_work`, and `StorySplitFlow`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.epics` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.story_splits` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.stories` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/main/nodes/fill.py::fill_work` @0a6247ab8773
- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow` @9e26ab4671cb

A blocked `StoryAuthor` result is not terminal for the drain. `Author.author_story` logs it and
marks the story's item `blocked`, so the other stories continue. The blocked item stays on the
work list for the completion gate.

This drain behavior is implemented by `Author.author_story`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.author_story` @41e4cc0d4cfc
- tests: `workflows/tests/author/test_workflow.py::test_a_story_nobody_can_fix_is_parked_and_the_epic_carries_on`
- tests: `workflows/tests/author/test_workflow.py::test_a_fresh_run_goes_split_epics_stories_then_finalizes`
- tests: `workflows/tests/author/test_workflow.py::test_a_run_stopped_at_a_later_epic_story_resumes_without_redoing_settled_rows`

### Completion gate
Finalize runs only when the milestone body still matches the digest recorded at the start and
every work-list item is done. The run writes the milestone's frontmatter but never its body, so a
changed digest means an operator edited the contract. In that case the machine waits on the author
context file, and the answer accepts the new body as the baseline. Unfinished items make the machine
wait on the same file with the list of each item's kind, id, status, and laps. The operator's
answer requeues those items with the answer as their note, and the machine runs the stages again
over the pending items. The operator mode `auto` does not skip either wait.

At its start the run also records the [epic baseline](../concepts/author-epic-baseline.md) with
`snapshot_epics`, next to the digest. The dispatcher passes it to `Finalize` as a JSON string.

The gate is implemented by `Author.complete`, `Author.requeue`, `contract_digest`,
`snapshot_epics`, `check_completion`, and `answer_below`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.complete` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.requeue` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/main/nodes/completion.py::contract_digest` @becb105386f9
- code: `workflows/src/workhorse_workflows/author/main/nodes/completion.py::check_completion` @becb105386f9
- code: `workflows/src/workhorse_workflows/author/shared/answer.py::answer_below` @719b34f0b1b0
- tests: `workflows/tests/author/test_workflow.py::test_an_audit_blocked_story_stops_at_the_completion_gate_and_nothing_finalizes`
- tests: `workflows/tests/author/test_workflow.py::test_an_edit_to_the_milestone_body_ends_at_the_contract_gate`
- tests: `workflows/tests/author/test_workflow.py::test_accepting_a_changed_contract_finishes_the_run`
- tests: `workflows/tests/author/test_workflow.py::test_auto_mode_does_not_skip_the_completion_gate`

The same dispatcher has two explicit non-epic branches. `mode=survey` hands off to `Surveyor` with
the rubric and survey directory and stops after discovery. `mode=parity-survey` hands off to
`ParitySurveyor` with its baseline inventory and survey directory and stops after that discovery.
`mode=story` seeds one open record of the [debt register](../../ostler/concepts/the-debt-register.md)
as a story in an existing epic, hands off to `StoryAuthor`, and then closes the record as promoted,
without running the epic stages or commit tail. The `record` input is a record id or short handle.
A token that names no record, and a record that is not open, fail the run before a story exists.
[Promoting a record](../concepts/promote-a-record.md) describes the path.

These non-epic branches are implemented by `Author.start`, `seed_story`, and `promote_record`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start` @41e4cc0d4cfc
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::seed_story` @ec2020d13cf3
- code: `workflows/src/workhorse_workflows/author/shared/nodes/story_mode.py::promote_record` @ec2020d13cf3
- code: `workflows/src/workhorse_workflows/author/shared/nodes/blueprint.py::blueprint` @f15f0a0f0ca5
- tests: workflows/tests/author/test_workflow.py::test_story_mode_promotes_an_open_record_and_does_not_commit_the_code_repo
- tests: workflows/tests/author/test_workflow.py::test_survey_mode_runs_the_surveyor_and_stops_at_discovery

The story branch hands `epic`, `record`, `layers`, and `services` to `seed_story`, then hands the
returned story slug and the current run directory to `StoryAuthor`. It closes the source record as
promoted after that handoff returns. The survey branches return `Done` immediately after
their handoff, while epic mode returns `Continue` into `split_epics`.

The story branch is implemented by `Author.start`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.start` @41e4cc0d4cfc

### Finalize
Finalization verifies reconciliation against the epic baseline taken at run start, whole-graph integrity, and that the milestone lists at least
one epic. It validates the authored artifacts again, advances the milestone from `approved` to
`authored` without rewriting its body, and commits the authored planning documents. A failed final validation commits
an incomplete marker instead of reporting a successful run.

The [author finalize subflow](../concepts/author-finalize-subflow.md) runs these gates in order. A
reconciliation or integrity failure is first offered to an automatic resolver up to its bounded
resolution count; human mode, exhausted resolution, or an escalated resolver response reaches the
operator context file. Only passing or explicitly skipped gates proceed to the next validation.

Finalization is implemented by `Finalize.close`, `validate_milestone_epics`,
`mark_milestone_authored`, `validate_artifacts`, `verify_integrity`, `verify_reconcile`, and
`commit_author`.

- code: `workflows/src/workhorse_workflows/author/finalize/flow.py::Finalize.close` @00fdb936a6a1
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::validate_milestone_epics` @cbdf7f3f88f8
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::mark_milestone_authored` @cbdf7f3f88f8
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/artifacts.py::validate_artifacts` @2caa87fcc660
- code: `workflows/src/workhorse_workflows/author/shared/nodes/integrity.py::verify_integrity` @ca330f6a9a15
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/artifacts.py::verify_reconcile` @2caa87fcc660
- code: `workflows/src/workhorse_workflows/author/shared/nodes/commit.py::commit_author` @d5269aa9b09f

When the completion gate finds a contract that held and no unfinished item, the dispatcher hands off
to `Finalize` and ends after its result.

This final dispatch behavior is implemented by `Author.complete`.

- code: `workflows/src/workhorse_workflows/author/main/flow.py::Author.complete` @41e4cc0d4cfc
- tests: `workflows/tests/author/test_workflow.py::test_epic_mode_authors_the_approved_milestone_and_commits_it`
