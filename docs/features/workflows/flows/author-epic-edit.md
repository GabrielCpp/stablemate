---
type: flow
slug: author-epic-edit
title: Author epic edit
---
# Author epic edit

The [workhorse-author run command](../workhorse-author.md#run) selects this flow from the
[author workflow composition root](../concepts/author-workflow-composition-root.md). It reconciles
one existing epic's journeys, seeds, stories, backlog ownership, and milestone references; the
feature book remains read-only during the edit.
The package implementation and its single deterministic-node registry are described in the
[author epic edit subflow](../concepts/author-epic-edit-subflow.md).

- start: an operator supplies an existing epic and a non-empty product-scope change to
  `workhorse-author run epic-edit`
- start: a story-edit handoff supplies a validated `add-story` or `remove-story` intent
- start: destructive reconciliation has `force: true` when the requested plan removes collateral
  stories or seeds, or a story beyond `Not started`
- steps:
  - [snapshot current epic](#snapshot-current-epic)
  - [plan the replacement](#plan-the-replacement)
  - [validate the projected graph](#validate-the-projected-graph)
  - [refine or gate invalid plans](#refine-or-gate-invalid-plans)
  - [review the approved plan](#review-the-approved-plan)
  - [apply and verify graph mutations](#apply-and-verify-graph-mutations)
  - [rewrite epic prose](#rewrite-epic-prose)
  - [author affected stories](#author-affected-stories)
  - [validate coverage and commit](#validate-coverage-and-commit)
- end: the requested epic edit is represented by consistent journeys, seeds, story contracts,
  dependencies, backlog ownership, and milestone references
- end: graph integrity passes before the `epic-edit` commit is created, or an unresolved validation
  or review failure is parked at an operator gate
- verify: emitted(event="refine-epic-edit-plan", count=1)
- verify: unchanged(subject="hand-authored story and epic prose")
- verify: removed(subject="the edited epic's milestone reference")
- verify: json_path(path="$.errors[*]", matches="E_FORCE_REQUIRED.*collateral (story|seed)")
- verify: removed(subject="the epic under the configured epics root")
- verify: removed(subject="the interrupted epic's milestone and backlog references")
- detail: [author workflow composition root](../concepts/author-workflow-composition-root.md)
- tests: workflows/tests/author/test_workflow.py::test_epic_edit_static_findings_drive_a_replacement_plan
- tests: ostler/tests/test_crud.py::test_update_story_rewrites_only_the_dependencies_section
- tests: ostler/tests/test_crud.py::test_delete_epic_removes_its_milestone_reference
- tests: workflows/tests/author/epic_edit/test_edit.py::test_plan_requires_force_for_removals_beyond_requested_story
- tests: workflows/tests/author/test_workflow.py::test_story_edit_follows_the_configured_epics_root
- tests: ostler/tests/test_crud.py::test_delete_epic_finishes_cleanup_after_interruption

## Phase Details

### Snapshot current epic
The start state is resolved through the configured document roots. The snapshot captures the epic
name, title, epic document hash, seeds and their metadata, stories and their body hashes, frozen
identities, and milestones that reference the epic.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.start`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::snapshot_epic`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/_blueprint.py::blueprint`

### Plan the replacement
A high-power planning turn receives the edit intent, snapshot, resolved epic directory, backlog,
and feature-book paths. It returns a complete typed replacement plan without editing repository
files. The plan contains journey changes, seed changes, story changes, deletion choice, and the
affected-story rewrite list.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.plan_edit`

### Validate the projected graph
Validation compares the snapshot hashes to the working tree, checks plan completion and epic
identity, rejects duplicate or missing change ids, projects seed and story sets, and rejects
dangling covers, dangling dependencies, orphaned active seeds, dependency cycles, unsatisfied
add/remove intent, frozen removals, unforced collateral removals, incorrect empty-epic deletion,
and omitted rewrites.

- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_edit_plan`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::_project`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::_cycle`

### Refine or gate invalid plans
Each static finding is passed with the rejected plan to a replacement planning turn. Three reworks
are allowed; a still-invalid plan awaits an operator and resumes at planning. Planner mutation of
the snapshotted epic or story bodies is a terminal workflow failure rather than a refinement case.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.validate_plan`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.refine_plan`

### Review the approved plan
Only a statically valid plan reaches the independent semantic reviewer. The reviewer checks actor
journeys, story-sized deliverables, and dependency order. An approved review proceeds to mutation;
a bounded needs-rework review returns to plan refinement, and an unresolved review awaits an operator.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.review_plan`

### Apply and verify graph mutations
Ostler removes requested stories and seeds, adds or updates seed metadata and story metadata, updates
milestone source items, and deletes the epic when both projected collections are empty. Applying the
same approved plan is safe for already-removed entities. Post-application validation compares actual
seed/story sets and metadata with the plan and hashes every unaffected story body for byte stability.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.apply_plan`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::apply_edit_plan`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_applied_edit`

### Rewrite epic prose
For a surviving epic, a model rewrites only human-owned prose. Parsed-document validation requires
the seven required epic sections and at least one user journey, while a second graph validation proves
the prose turn did not alter the approved structural graph. Failure reworks three times, then awaits.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.rewrite_epic`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_epic_document`

### Author affected stories
The approved affected list is consumed in order. Each existing or newly added story may receive a
story-local mockup, is authored, structurally and contextually validated, and independently audited.
Validation or audit findings are recorded in the story attempt ledger and reworked up to three times;
an unresolved story is parked at its story context. Unaffected stories are never rewritten.

- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::select_affected_story`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.design_mockup`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.write_story`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.check_story`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.audit_story`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.rework_story`

### Validate coverage and commit
The surviving epic must pass deterministic coverage and semantic coverage review, then whole-graph
integrity. An add-story handoff prunes its consumed backlog bullet only after integrity succeeds;
the flow commits the `epic-edit` change. An empty approved epic skips prose and story work and is
deleted before the same integrity and commit tail.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.check_coverage`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.finish`
