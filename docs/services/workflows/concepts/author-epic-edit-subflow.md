---
type: concept
slug: author-epic-edit-subflow
title: Author epic edit subflow
---
# Author epic edit subflow

The `epic_edit` package is the named reconciliation subflow used by the author workflow and by
story-edit handoffs. Its `EpicEdit` machine snapshots one epic, obtains and validates a typed
replacement plan, applies only the approved graph delta, rewrites affected prose, and commits
only after coverage and integrity checks pass. The package-local node registry is deliberately
separate from the parent workflow registry: `blueprint` is the single registration target for
the deterministic nodes owned by this subflow.

For the direct-versus-handoff entry context, see [epic edit invocation
selection](epic-edit-invocation-selection.md).

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit` @2882a05baa0b
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/__init__.py` @3974010406ba
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/_blueprint.py::blueprint` @2f9e682267f2
- tests: `workflows/tests/author/epic_edit/test_edit.py::test_plan_requires_force_for_removals_beyond_requested_story`
- detail: [epic edit concept selection](epic-edit-concept-selection.md)

## Fields

### epic
- type: string
- default: empty string
- required: false
- semantics: direct invocation's epic identifier
- verify: json_path(path="$.epic", equals="acme-epic")
- semantics: ignored when `intent.epic` is already set
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit` @2882a05baa0b
- detail: [epic edit input selection](epic-edit-input-selection.md)

### change
- type: string
- default: empty string
- required: false
- semantics: direct invocation's requested scope change
- verify: json_path(path="$.change", equals="example change")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit` @2882a05baa0b
- detail: [epic edit input selection](epic-edit-input-selection.md)

### intent
- type: `EditIntent`
- default: an empty `EditIntent`
- required: false
- semantics: validated edit binding supplied by a story-edit handoff or constructed from direct parameters
- verify: json_path(path="$.intent", equals="example intent")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit` @2882a05baa0b
- detail: [epic edit input selection](epic-edit-input-selection.md)

### force
- type: boolean
- default: false
- required: false
- semantics: permits explicitly requested collateral or frozen-scope removal according to plan validation
- verify: json_path(path="$.force", equals=false)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit` @2882a05baa0b
- detail: [epic edit input selection](epic-edit-input-selection.md)

### operator_mode
- type: string
- default: auto
- required: false
- semantics: operator-routing mode carried by the workflow runtime
- verify: json_path(path="$.operator_mode", equals="auto")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit` @2882a05baa0b
- detail: [epic edit input selection](epic-edit-input-selection.md)

## Methods

### setup
- sig: `setup() -> RunContext`
- does: loads author configuration in `epic-edit` mode
- returns: returns a `RunContext` populated from the loaded configuration
- verify: json_path(path="$.mode", equals="epic-edit")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.setup` @2882a05baa0b

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the explicit epic or the handoff intent's epic
- returns: returns matching `work_id` and `epic` labels
- verify: count(subject="epic-edit labeled runs", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.labels` @2882a05baa0b

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines epic labels with telemetry labels for the `epic_edit` machine
- does: includes the `reworks` budget counter label when present in state parameters
- does: omits `reworks` (and every other budget counter) when the state carries it at the default of zero, so a span cannot be silently bucketed as a first attempt for a budget the flow has not spent
- returns: returns labels used for state telemetry
- verify: count(subject="epic-edit state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.state_labels` @2882a05baa0b
- tests: `workflows/tests/coder/test_telemetry.py::test_epic_edit_reports_reworks_and_omits_defaulted_absent_counters`

### blueprint
- sig: `Blueprint("author-epic-edit") -> Blueprint`
- does: provides the one node-registration target owned by the epic-edit package
- returns: returns a blueprint named `author-epic-edit`
- verify: json_path(path="$.name", equals="author-epic-edit")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/_blueprint.py::blueprint` @2f9e682267f2

### start
- sig: `start() -> Continue`
- does: rejects a direct invocation missing either the epic or the change
- does: converts direct parameters into an `EditIntent` when no handoff intent was supplied
- does: snapshots the selected epic before planning
- returns: returns a continuation targeting `plan_edit` with the intent and snapshot
- verify: count(subject="epic-edit starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.start` @2882a05baa0b

### plan_edit
- sig: `plan_edit(intent: EditIntent, snapshot: EpicSnapshot) -> Continue`
- does: reads the open records of the debt register through `read_register_listing` and passes the listing to the planning agent
- does: asks the planning agent for a complete typed replacement plan without mutating repository files
- returns: returns a continuation targeting `validate_plan`
- verify: count(subject="epic-edit replacement plans", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.plan_edit` @2882a05baa0b

### validate_plan
- sig: `validate_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, reworks: int = 0) -> Continue | Await`
- does: rejects planner mutation of snapshotted epic or story bodies as a workflow failure
- does: refines an invalid plan up to three times
- does: parks an invalid plan at the operator gate after refinement is exhausted
- does: forwards a valid plan to semantic review
- returns: returns a continuation for refinement or review, or `Await`
- verify: count(subject="epic-edit plan validation outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.validate_plan` @2882a05baa0b

### refine_plan
- sig: `refine_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, findings: str, reworks: int = 0) -> Continue`
- does: sends validation findings and the prior plan to a replacement planning turn
- returns: returns a continuation targeting `validate_plan` with an incremented rework count
- verify: count(subject="epic-edit plan refinements", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.refine_plan` @2882a05baa0b

### review_plan
- sig: `review_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, reworks: int = 0) -> Continue | Await`
- does: hands only a statically valid plan to the [PM review](author-pm-review.md) at the `epic-edit-plan` stage
- does: routes an approved review to mutation
- does: returns the findings to plan refinement while fewer than three reworks were used
- does: parks an unresolved review at the operator gate on the run's context file
- returns: returns a continuation for application or refinement, or `Await`
- verify: count(subject="epic-edit plan reviews", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.review_plan` @2882a05baa0b

### apply_plan
- sig: `apply_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan) -> Continue`
- does: applies the approved graph plan through the edit nodes
- verify: count(subject="epic-edit plan applications", equals=1)
- does: fails the run with `failure_class="epic-edit-application-drift"` and the validation errors when post-application state differs from the approved plan
- verify: count(subject="epic-edit application drift failures", equals=1)
- does: skips prose and story authoring by continuing to `finish` when the applied edit deleted the epic
- verify: count(subject="epic-edit finishes after a deleted epic", equals=1)
- does: continues to `rewrite_epic` with `intent`, `snapshot`, `plan`, and `applied` when the applied edit kept the epic
- verify: count(subject="epic-edit rewrites after a kept epic", equals=1)
- returns: returns a continuation targeting `finish` (deleted epic) or `rewrite_epic` (surviving epic)
- verify: json_path(path="$.next_state", matches="^(finish|rewrite_epic)$")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.apply_plan` @2882a05baa0b

### rewrite_epic
- sig: `rewrite_epic(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, applied: AppliedEpicEdit, findings: str = "", reworks: int = 0) -> Continue | Await`
- does: asks the agent to rewrite surviving epic prose
- does: validates required epic sections and at least one user journey
- does: rejects prose changes that alter the approved structural graph
- does: retries invalid prose up to three times and then parks at the operator gate
- returns: returns a continuation targeting affected-story selection, or `Await`
- verify: count(subject="epic-edit epic rewrites", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.rewrite_epic` @2882a05baa0b

### next_affected_story
- sig: `next_affected_story(intent: EditIntent, applied: AppliedEpicEdit, index: int = 0) -> Continue`
- does: enters the affected-story loop at the first affected story (`index=0` default) and advances the index on each re-entry
- does: routes to `check_coverage` with `intent` and `applied` when the affected-story list is exhausted (`pick.has_story` is false)
- does: continues to `design_mockup` with `intent`, `applied`, `pick`, and `index` when an affected story is selected
- returns: returns a continuation targeting `check_coverage` (exhausted) or `design_mockup` (selected)
- verify: count(subject="epic-edit affected-story selections", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.next_affected_story` @2882a05baa0b

### design_mockup
- sig: `design_mockup(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int) -> Continue`
- does: asks the design agent for a story-local mockup before story authoring
- does: continues to `write_story` with `intent`, `applied`, `pick`, `index`, and the produced `mockup`
- returns: returns a continuation targeting `write_story` with the mockup result
- verify: count(subject="epic-edit mockup designs", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.design_mockup` @2882a05baa0b

### write_story
- sig: `write_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, mockup: str = "", reworks: int = 0) -> Continue | Await`
- does: asks the agent to author the selected story body
- does: parks a blocked story at the operator gate on the run's context file
- returns: returns a continuation targeting story validation or `Await`
- verify: count(subject="epic-edit story writes", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.write_story` @2882a05baa0b

### check_story
- sig: `check_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, mockup: str = "", reworks: int = 0) -> Continue | Await`
- does: validates story structure and grounding before the PM reviews it
- does: records validation attempts and reworks invalid stories up to three times
- does: parks an unresolved story at the operator gate on the run's context file
- returns: returns a continuation targeting review or rework, or `Await`
- verify: count(subject="epic-edit story validation outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.check_story` @2882a05baa0b

### review_story
- sig: `review_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, mockup: str = "", reworks: int = 0, prior: str = "") -> Continue | Await`
- does: hands the authored story to the [PM review](author-pm-review.md) at the `story` stage with the previous findings
- verify: count(subject="epic-edit story reviews", equals=1)
- does: reworks failed reviews within the bounded budget and parks exhausted failures at the operator gate
- does: advances to the next affected story after a passing review
- returns: returns a continuation targeting rework or selection, or `Await`
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.review_story` @2882a05baa0b

### rework_story
- sig: `rework_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, findings: str, mockup: str = "", reworks: int = 0) -> Continue`
- does: records the review findings and asks the story agent for a corrected body
- returns: returns a continuation targeting `check_story` with an incremented rework count
- verify: count(subject="epic-edit story reworks", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.rework_story` @2882a05baa0b

### check_coverage
- sig: `check_coverage(intent: EditIntent, applied: AppliedEpicEdit) -> Continue`
- does: rejects the resulting epic when deterministic coverage fails
- does: rejects the resulting epic when the PM review of the story split does not pass
- returns: returns a continuation targeting `finish` after both coverage gates pass
- verify: count(subject="epic-edit coverage gates", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.check_coverage` @2882a05baa0b

### finish
- sig: `finish(intent: EditIntent, applied: AppliedEpicEdit) -> Done`
- does: verifies whole-graph integrity before publishing the edit
- does: closes the record of an add-story intent as promoted only after integrity succeeds, naming the new story and its epic
- does: commits the `epic-edit` change after all required checks pass
- returns: returns `Done` with the applied edit
- verify: count(subject="completed epic edits", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.finish` @2882a05baa0b
- tests: `workflows/tests/author/test_workflow.py::test_epic_edit_add_story_from_a_record_closes_it_as_promoted`

## Nodes

The deterministic nodes owned by the epic-edit package are registered with the `blueprint` instance. These nodes handle snapshot capture, plan validation, application, and result verification in the edit workflow.

### method: read_register_listing
- sig: `read_register_listing(logger: logging.Logger, repo_dir: str = "") -> RegisterListing`
- does: lists the open records of every repository on the [debt register](../../ostler/concepts/the-debt-register.md), one tab-separated line each under the header `id`, `repo`, `area`, `status`, `pattern`, `summary`
- verify: json_path(path="$.text", matches="^id\\trepo\\tarea\\tstatus\\tpattern\\tsummary")
- does: returns the text `no open records` when the register holds none
- verify: json_path(path="$.text", equals="no open records")
- returns: returns a `RegisterListing` holding the listing text
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::read_register_listing` @85ab2cf6cdff
- code: `workflows/src/workhorse_workflows/author/shared/listing.py::open_listing` @85958b15a6c1
- tests: `workflows/tests/author/test_workflow.py::test_the_epic_edit_planner_reads_the_register_listing_of_a_filed_record`
- tests: `workflows/tests/author/test_workflow.py::test_the_epic_edit_planner_is_told_when_the_register_is_empty`

### method: snapshot_epic
- sig: `snapshot_epic(logger: logging.Logger, epic: str = "", repo_dir: str = "") -> EpicSnapshot`
- does: captures epic metadata
- verify: json_path(path="$.epic_hash", matches="^[0-9a-f]{64}$")
- does: captures seed metadata
- verify: json_path(path="$.seeds", equals="example seeds")
- does: captures story metadata
- verify: json_path(path="$.stories", equals="example stories")
- does: captures story body hashes
- verify: json_path(path="$.stories[*].body_hash", matches="^[0-9a-f]{64}$")
- does: captures frozen seed identities
- verify: json_path(path="$.seeds[*].frozen", matches="^(true|false)$")
- does: captures frozen story identities
- verify: json_path(path="$.stories[*].frozen", matches="^(true|false)$")
- does: captures referencing milestones
- verify: json_path(path="$.milestones", equals="example milestones")
- raises: raises `WorkflowFailed` when the epic does not exist
- returns: returns the baseline used to validate planning and application
- verify: created(subject="an epic edit snapshot")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::snapshot_epic` @85ab2cf6cdff

### method: validate_edit_plan
- sig: `validate_edit_plan(logger: logging.Logger, intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, repo_dir: str = "") -> Defects`
- does: rejects incomplete, wrong-epic, duplicate, missing-id, dangling-cover, dangling-dependency, orphan-seed, cyclic, unsatisfied, frozen, unforced, deletion, and omitted-rewrite plans
- returns: returns `Defects(ok=True)` only when the projected graph satisfies all edit constraints
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_edit_plan` @85ab2cf6cdff

### method: apply_edit_plan
- sig: `apply_edit_plan(logger: logging.Logger, intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, repo_dir: str = "") -> AppliedEpicEdit`
- does: removes, adds, or updates stories and seeds through Ostler
- does: updates milestone source-item ownership for removed or added source records, naming a record by its id
- does: deletes an epic when the approved resulting seed and story sets are empty
- does: safely skips already-removed entities when the same approved plan is reapplied
- returns: returns the applied epic identity and affected and removed story lists
- verify: persists(subject="the approved epic graph delta")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::apply_edit_plan` @85ab2cf6cdff

### validate_applied_edit
This validation returns `Defects(ok=True)` when the on-disk graph matches the approved delta.

- sig: `validate_applied_edit(logger: logging.Logger, snapshot: EpicSnapshot, plan: EpicEditPlan, applied: AppliedEpicEdit, repo_dir: str = "") -> Defects`
- does: compares resulting seed and story identities and metadata with the approved projection
- does: requires every unaffected story body to remain byte-stable
- verify: unchanged(subject="unaffected story bodies")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_applied_edit` @85ab2cf6cdff
- detail: [applied edit validation](applied-edit-validation.md)

### method: validate_epic_document
- sig: `validate_epic_document(logger: logging.Logger, epic_dir: str = "", repo_dir: str = "") -> Defects`
- does: requires all seven epic sections to exist and contain content
- does: requires at least one child journey under `User Journeys`
- returns: returns `Defects(ok=True)` only when the human-owned epic prose is structurally valid
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_epic_document` @85ab2cf6cdff

### select_affected_story
- sig: `select_affected_story(logger: logging.Logger, epic: str, affected_stories: list[str], index: int, repo_dir: str = "") -> StoryChoice`
- does: resolves the indexed affected story through Ostler
- consistency: affected-story-list — when the index reaches the approved affected-story list length, returns `StoryChoice(has_story=False, reason="every affected story is authored")`
- verify: json_path(path="$.has_story", equals=False)
- raises: raises `WorkflowFailed` when an approved affected story no longer exists
- returns: returns the story path, slug, directory, progress, and remaining count
- verify: count(subject="selected affected stories", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::select_affected_story` @85ab2cf6cdff
- detail: [affected story selection](affected-story-selection.md)
