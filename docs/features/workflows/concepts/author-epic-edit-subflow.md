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

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/__init__.py`
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/epic_edit/test_edit.py::test_plan_requires_force_for_removals_beyond_requested_story`
- detail: [epic edit concept selection](epic-edit-concept-selection.md)

## Fields

### epic
- type: string
- default: empty string
- required: false
- semantics: direct invocation's epic identifier
- verify: json_path(path="$.epic", matches=".*")
- semantics: ignored when `intent.epic` is already set
- verify: json_path(path="$.epic", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- detail: [epic edit input selection](epic-edit-input-selection.md)

### change
- type: string
- default: empty string
- required: false
- semantics: direct invocation's requested scope change
- verify: json_path(path="$.change", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- detail: [epic edit input selection](epic-edit-input-selection.md)

### intent
- type: `EditIntent`
- default: an empty `EditIntent`
- required: false
- semantics: validated edit binding supplied by a story-edit handoff or constructed from direct parameters
- verify: json_path(path="$.intent", matches=".*")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- detail: [epic edit input selection](epic-edit-input-selection.md)

### force
- type: boolean
- default: false
- required: false
- semantics: permits explicitly requested collateral or frozen-scope removal according to plan validation
- verify: json_path(path="$.force", equals=false)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- detail: [epic edit input selection](epic-edit-input-selection.md)

### operator_mode
- type: string
- default: auto
- required: false
- semantics: operator-routing mode carried by the workflow runtime
- verify: json_path(path="$.operator_mode", equals="auto")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- detail: [epic edit input selection](epic-edit-input-selection.md)

## Methods

### setup
- sig: `setup() -> RunContext`
- does: loads author configuration in `epic-edit` mode
- returns: returns a `RunContext` populated from the loaded configuration
- verify: json_path(path="$.mode", equals="epic-edit")
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the explicit epic or the handoff intent's epic
- returns: returns matching `work_id` and `epic` labels
- verify: count(subject="epic-edit labeled runs", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.labels`

### state_labels
- sig: `state_labels(params: dict[str, Any]) -> dict[str, str]`
- does: combines epic labels with telemetry labels for the `epic_edit` machine
- does: includes the `reworks` budget counter label when present in state parameters
- does: omits `reworks` (and every other budget counter) when the state carries it at the default of zero, so a span cannot be silently bucketed as a first attempt for a budget the flow has not spent
- returns: returns labels used for state telemetry
- verify: count(subject="epic-edit state label sets", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.state_labels`
- tests: `workflows/tests/coder/test_telemetry.py::test_epic_edit_reports_reworks_and_omits_defaulted_absent_counters`

### blueprint
- sig: `Blueprint("author-epic-edit") -> Blueprint`
- does: provides the one node-registration target owned by the epic-edit package
- returns: returns a blueprint named `author-epic-edit`
- verify: json_path(path="$.name", equals="author-epic-edit")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/_blueprint.py::blueprint`

### start
- sig: `start() -> Continue`
- does: rejects a direct invocation missing either the epic or the change
- does: converts direct parameters into an `EditIntent` when no handoff intent was supplied
- does: snapshots the selected epic before planning
- returns: returns a continuation targeting `plan_edit` with the intent and snapshot
- verify: count(subject="epic-edit starts", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.start`

### plan_edit
- sig: `plan_edit(intent: EditIntent, snapshot: EpicSnapshot) -> Continue`
- does: asks the planning agent for a complete typed replacement plan without mutating repository files
- returns: returns a continuation targeting `validate_plan`
- verify: count(subject="epic-edit replacement plans", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.plan_edit`

### validate_plan
- sig: `validate_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, reworks: int = 0) -> Continue | Await`
- does: rejects planner mutation of snapshotted epic or story bodies as a workflow failure
- does: refines an invalid plan up to three times
- does: parks an invalid plan at the operator gate after refinement is exhausted
- does: forwards a valid plan to semantic review
- returns: returns a continuation for refinement or review, or `Await`
- verify: count(subject="epic-edit plan validation outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.validate_plan`

### refine_plan
- sig: `refine_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, findings: str, reworks: int = 0) -> Continue`
- does: sends validation findings and the prior plan to a replacement planning turn
- returns: returns a continuation targeting `validate_plan` with an incremented rework count
- verify: count(subject="epic-edit plan refinements", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.refine_plan`

### review_plan
- sig: `review_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, reworks: int = 0) -> Continue | Await`
- does: submits only a statically valid plan to the semantic reviewer
- does: routes an approved review to mutation
- does: returns a bounded rework review to plan refinement
- does: parks an unresolved review at the operator gate
- returns: returns a continuation for application or refinement, or `Await`
- verify: count(subject="epic-edit plan reviews", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.review_plan`

### apply_plan
- sig: `apply_plan(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan) -> Continue`
- does: applies the approved graph plan through the edit nodes
- does: fails the run with `failure_class="epic-edit-application-drift"` and the validation errors when post-application state differs from the approved plan
- does: skips prose and story authoring by continuing to `finish` when the applied edit deleted the epic
- does: continues to `rewrite_epic` with `intent`, `snapshot`, `plan`, and `applied` when the applied edit kept the epic
- returns: returns a continuation targeting `finish` (deleted epic) or `rewrite_epic` (surviving epic)
- verify: count(subject="epic-edit plan applications", equals=1)
- verify: count(subject="epic-edit application drift failures", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.apply_plan`

### rewrite_epic
- sig: `rewrite_epic(intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, applied: AppliedEpicEdit, findings: str = "", reworks: int = 0) -> Continue | Await`
- does: asks the agent to rewrite surviving epic prose
- does: validates required epic sections and at least one user journey
- does: rejects prose changes that alter the approved structural graph
- does: retries invalid prose up to three times and then parks at the operator gate
- returns: returns a continuation targeting affected-story selection, or `Await`
- verify: count(subject="epic-edit epic rewrites", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.rewrite_epic`

### next_affected_story
- sig: `next_affected_story(intent: EditIntent, applied: AppliedEpicEdit, index: int = 0) -> Continue`
- does: enters the affected-story loop at the first affected story (`index=0` default) and advances the index on each re-entry
- does: routes to `check_coverage` with `intent` and `applied` when the affected-story list is exhausted (`pick.has_story` is false)
- does: continues to `design_mockup` with `intent`, `applied`, `pick`, and `index` when an affected story is selected
- returns: returns a continuation targeting `check_coverage` (exhausted) or `design_mockup` (selected)
- verify: count(subject="epic-edit affected-story selections", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.next_affected_story`

### design_mockup
- sig: `design_mockup(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int) -> Continue`
- does: asks the design agent for a story-local mockup before story authoring
- does: continues to `write_story` with `intent`, `applied`, `pick`, `index`, and the produced `mockup`
- returns: returns a continuation targeting `write_story` with the mockup result
- verify: count(subject="epic-edit mockup designs", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.design_mockup`

### write_story
- sig: `write_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, mockup: str = "", reworks: int = 0) -> Continue | Await`
- does: asks the agent to author the selected story body
- does: parks a blocked story at its story context
- returns: returns a continuation targeting story validation or `Await`
- verify: count(subject="epic-edit story writes", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.write_story`

### check_story
- sig: `check_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, mockup: str = "", reworks: int = 0) -> Continue | Await`
- does: validates story structure and grounding before auditing it
- does: records validation attempts and reworks invalid stories up to three times
- does: parks an unresolved story at its story context
- returns: returns a continuation targeting audit or rework, or `Await`
- verify: count(subject="epic-edit story validation outcomes", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.check_story`

### audit_story
- sig: `audit_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, mockup: str = "", reworks: int = 0) -> Continue | Await`
- does: independently audits the authored story
- does: reworks failed audits within the bounded budget and parks exhausted failures
- does: advances to the next affected story after a passing audit
- returns: returns a continuation targeting rework or selection, or `Await`
- verify: count(subject="epic-edit story audits", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.audit_story`

### rework_story
- sig: `rework_story(intent: EditIntent, applied: AppliedEpicEdit, pick: StoryChoice, index: int, findings: str, mockup: str = "", reworks: int = 0) -> Continue`
- does: records the audit findings and asks the story agent for a corrected body
- returns: returns a continuation targeting `check_story` with an incremented rework count
- verify: count(subject="epic-edit story reworks", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.rework_story`

### check_coverage
- sig: `check_coverage(intent: EditIntent, applied: AppliedEpicEdit) -> Continue`
- does: rejects the resulting epic when deterministic coverage fails
- does: rejects the resulting epic when semantic coverage review is not `ok`
- returns: returns a continuation targeting `finish` after both coverage gates pass
- verify: count(subject="epic-edit coverage gates", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.check_coverage`

### finish
- sig: `finish(intent: EditIntent, applied: AppliedEpicEdit) -> Done`
- does: verifies whole-graph integrity before publishing the edit
- does: prunes an add-story backlog bullet only after integrity succeeds
- does: commits the `epic-edit` change after all required checks pass
- returns: returns `Done` with the applied edit
- verify: count(subject="completed epic edits", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit.finish`

## Nodes

The deterministic nodes owned by the epic-edit package are registered with the `blueprint` instance. These nodes handle snapshot capture, plan validation, application, and result verification in the edit workflow.

### method: snapshot_epic
- sig: `snapshot_epic(logger: logging.Logger, epic: str = "", repo_dir: str = "") -> EpicSnapshot`
- does: captures epic metadata
- verify: json_path(path="$.epic_hash", matches="^[0-9a-f]{64}$")
- does: captures seed metadata
- verify: json_path(path="$.seeds", matches=".*")
- does: captures story metadata
- verify: json_path(path="$.stories", matches=".*")
- does: captures story body hashes
- verify: json_path(path="$.stories[*].body_hash", matches="^[0-9a-f]{64}$")
- does: captures frozen seed identities
- verify: json_path(path="$.seeds[*].frozen", matches="^(true|false)$")
- does: captures frozen story identities
- verify: json_path(path="$.stories[*].frozen", matches="^(true|false)$")
- does: captures referencing milestones
- verify: json_path(path="$.milestones", matches=".*")
- raises: raises `WorkflowFailed` when the epic does not exist
- returns: returns the baseline used to validate planning and application
- verify: created(subject="an epic edit snapshot")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::snapshot_epic`

### method: validate_edit_plan
- sig: `validate_edit_plan(logger: logging.Logger, intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, repo_dir: str = "") -> Defects`
- does: rejects incomplete, wrong-epic, duplicate, missing-id, dangling-cover, dangling-dependency, orphan-seed, cyclic, unsatisfied, frozen, unforced, deletion, and omitted-rewrite plans
- returns: returns `Defects(ok=True)` only when the projected graph satisfies all edit constraints
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_edit_plan`

### method: apply_edit_plan
- sig: `apply_edit_plan(logger: logging.Logger, intent: EditIntent, snapshot: EpicSnapshot, plan: EpicEditPlan, repo_dir: str = "") -> AppliedEpicEdit`
- does: removes, adds, or updates stories and seeds through Ostler
- does: updates milestone source-item ownership for removed or added source bullets
- does: deletes an epic when the approved resulting seed and story sets are empty
- does: safely skips already-removed entities when the same approved plan is reapplied
- returns: returns the applied epic identity and affected and removed story lists
- verify: persists(subject="the approved epic graph delta")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::apply_edit_plan`

### validate_applied_edit
This validation returns `Defects(ok=True)` when the on-disk graph matches the approved delta.

- sig: `validate_applied_edit(logger: logging.Logger, snapshot: EpicSnapshot, plan: EpicEditPlan, applied: AppliedEpicEdit, repo_dir: str = "") -> Defects`
- does: compares resulting seed and story identities and metadata with the approved projection
- does: requires every unaffected story body to remain byte-stable
- verify: unchanged(subject="unaffected story bodies")
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_applied_edit`
- detail: [applied edit validation](applied-edit-validation.md)

### method: validate_epic_document
- sig: `validate_epic_document(logger: logging.Logger, epic_dir: str = "", repo_dir: str = "") -> Defects`
- does: requires all seven epic sections to exist and contain content
- does: requires at least one child journey under `User Journeys`
- returns: returns `Defects(ok=True)` only when the human-owned epic prose is structurally valid
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::validate_epic_document`

### select_affected_story
- sig: `select_affected_story(logger: logging.Logger, epic: str, affected_stories: list[str], index: int, repo_dir: str = "") -> StoryChoice`
- does: resolves the indexed affected story through Ostler
- consistency: affected-story-list — when the index reaches the approved affected-story list length, returns `StoryChoice(has_story=False, reason="every affected story is authored")`
- verify: json_path(path="$.has_story", equals=False)
- raises: raises `WorkflowFailed` when an approved affected story no longer exists
- returns: returns the story path, slug, directory, progress, and remaining count
- verify: count(subject="selected affected stories", equals=1)
- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::select_affected_story`
- detail: [affected story selection](affected-story-selection.md)
