---
type: concept
slug: author-milestone-subflow
title: Author milestone subflow
---
# Author milestone subflow

The milestone subflow is the authoring boundary for exactly one approved roadmap milestone. It
resolves the repository and roadmap during setup, snapshots all existing milestone and epic
documents, gives one agent turn permission to create or reuse only the roadmap-owned milestone,
and validates that no epic or unrelated milestone changed. A blocked agent response or a failed
validation returns to the same agent state through an operator-awaiting context file.

- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone`
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/_blueprint.py::blueprint`
- tests: `workflows/tests/author/milestone/test_flow.py::test_builds_then_reuses_one_milestone_without_epics`
- detail: [build milestone prompt](../build-milestone-prompt.md)
- detail: [milestone context](../milestone-context.md)
- detail: [milestone result](../milestone-result.md)
- detail: [milestone validation](../milestone-validation.md)

## Nodes

### blueprint
- sig: `Blueprint("author-milestone") -> Blueprint`
- does: provides the registration target for the milestone nodes
- emits: a blueprint named `author-milestone`
- verify: json_path(path="$.name", equals="author-milestone")
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/_blueprint.py::blueprint`

### method: prepare_milestone
- sig: `prepare_milestone(logger: logging.Logger, repo_dir: str = "") -> MilestoneContext`
- does: resolves the repository root and requires an approved roadmap
- verify: count(subject="approved roadmap resolutions", equals=1)
- does: rejects intake when the roadmap already sources more than one milestone
- verify: count(subject="duplicate-roadmap preparation failures", equals=1)
- does: snapshots every milestone document fingerprint
- verify: count(subject="snapshotted milestone documents", equals=1)
- does: snapshots every epic document fingerprint
- verify: count(subject="snapshotted epic documents", equals=1)
- returns: returns the approved roadmap and resolved epic directory
- verify: json_path(path="$.roadmap", matches=".+")
- verify: json_path(path="$.epics_dir", matches=".+")
- returns: returns the existing milestone identity and epic list
- verify: json_path(path="$.milestone_path", matches="^(|docs/.+)$")
- verify: json_path(path="$.milestone_epics", matches="^\\[.*\\]$")
- returns: returns the milestone and epic fingerprint maps
- verify: json_path(path="$.milestone_fingerprints", matches="^\\{.*\\}$")
- verify: json_path(path="$.epic_fingerprints", matches="^\\{.*\\}$")
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/milestone.py::prepare_milestone`

### method: validate_milestone
- sig: `validate_milestone(logger: logging.Logger, context: MilestoneContext) -> MilestoneValidation`
- does: requires exactly one milestone sourced by the prepared roadmap
- verify: count(subject="roadmap-owned milestones", equals=1)
- does: requires the roadmap to be the milestone's sole source item
- verify: json_path(path="$.sourceItems", matches="^\\['docs/roadmaps/account-access\\.md'\\]$")
- does: requires the milestone epic list to preserve the prepared order
- verify: unchanged(subject="milestone epics", except_fields=[])
- does: rejects creation or modification of unrelated milestone documents
- verify: unchanged(subject="unrelated milestone documents", except_fields=[])
- does: rejects creation or modification of epic documents
- verify: unchanged(subject="epic documents", except_fields=[])
- returns: returns `ok`, the authored milestone path, whether it was reused, and newline-separated errors
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/milestone.py::validate_milestone`

## Methods

### setup
- sig: `setup() -> MilestoneContext`
- does: calls `prepare_milestone` to resolve the consuming repository and approved roadmap
- verify: count(subject="approved roadmap preparations", equals=1)
- does: returns the [milestone context](../milestone-context.md) containing the roadmap, resolved epic directory, existing roadmap-owned milestone state, and pre-turn fingerprints
- verify: json_path(path="$.roadmap", matches=".+")
- returns: returns the prepared context before any agent turn runs
- verify: json_path(path="$.epics_dir", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the roadmap filename stem as `work_id`
- returns: returns `{"work_id": Path(roadmap).stem}`
- verify: json_path(path="$.work_id", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.labels`

### start
- sig: `start() -> Done | Await`
- does: asks one high-power agent turn to create or reuse the roadmap-owned milestone
- verify: count(subject="milestone authoring agent turns", equals=1)
- does: renders the [build milestone prompt](../build-milestone-prompt.md) with the approved roadmap as `roadmap`
- verify: json_path(path="$.roadmap", matches=".+")
- does: requests a `MilestoneResult` response with high agent power and runs the turn from the repository root
- verify: json_path(path="$.status", matches="^(complete|blocked)$")
- does: routes a blocked agent result to the operator-awaiting context file with the agent notes and the same start callback
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: validates a non-blocked agent result before completing
- verify: count(subject="milestone validations", equals=1)
- does: routes failed milestone validation to the operator-awaiting context file with all validation errors and the same start callback
- verify: visible(locator="operator-awaiting context", text="milestone")
- does: completes with the validation result when the milestone passes all ownership and immutability checks
- verify: json_path(path="$.ok", equals=True)
- returns: returns `Done` with the [milestone validation](../milestone-validation.md) when validation succeeds, otherwise `Await` resuming `start`
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`
