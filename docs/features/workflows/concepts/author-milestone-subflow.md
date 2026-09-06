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
- detail: [milestone context](../milestone-context.md)
- detail: [milestone result](../milestone-result.md)
- detail: [milestone validation](../milestone-validation.md)

## Methods

### blueprint
- sig: `Blueprint("author-milestone") -> Blueprint`
- does: provides the registration target for the milestone nodes
- returns: returns a blueprint named `author-milestone`
- verify: json_path(path="$.name", equals="author-milestone")
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/_blueprint.py::blueprint`

### setup
- sig: `setup() -> MilestoneContext`
- does: prepares and snapshots the approved roadmap and planning graph
- returns: returns the [milestone context](../milestone-context.md) used by the flow
- verify: count(subject="prepared milestone contexts", equals=1)
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.setup`

### labels
- sig: `labels() -> dict[str, str]`
- does: labels the run with the roadmap filename stem as `work_id`
- returns: returns `{"work_id": Path(roadmap).stem}`
- verify: json_path(path="$.work_id", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.labels`

### start
- sig: `start() -> Done | Await`
- does: asks the agent to create or reuse the roadmap-owned milestone
- verify: count(subject="milestone authoring agent turns", equals=1)
- does: routes a blocked agent result to the operator-awaiting context file
- verify: visible(locator="operator-awaiting context", text="blocked")
- does: validates the authored milestone before completing
- verify: count(subject="milestone validations", equals=1)
- returns: returns `Done` with validation when validation succeeds
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`

### prepare_milestone
- sig: `prepare_milestone(logger: logging.Logger, repo_dir: str = "") -> MilestoneContext`
- does: resolves the repository root and requires an approved roadmap
- verify: count(subject="approved roadmap resolutions", equals=1)
- does: rejects intake when the roadmap already sources more than one milestone
- verify: count(subject="duplicate-roadmap preparation failures", equals=1)
- does: snapshots every milestone document fingerprint
- verify: count(subject="snapshotted milestone documents", equals=1)
- does: snapshots every epic document fingerprint
- verify: count(subject="snapshotted epic documents", equals=1)
- returns: returns the roadmap, resolved paths, existing milestone identity and epic list, and both fingerprint maps
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/milestone.py::prepare_milestone`

### validate_milestone
- sig: `validate_milestone(logger: logging.Logger, context: MilestoneContext) -> MilestoneValidation`
- does: requires exactly one milestone sourced by the prepared roadmap
- verify: count(subject="roadmap-owned milestones", equals=1)
- does: requires the roadmap to be the milestone's sole source item
- verify: json_path(path="$.sourceItems", equals=["docs/roadmaps/account-access.md"])
- does: requires the milestone epic list to preserve the prepared order
- verify: unchanged(subject="milestone epics", except_fields=[])
- does: rejects creation or modification of unrelated milestone documents
- verify: unchanged(subject="unrelated milestone documents", except_fields=[])
- does: rejects creation or modification of epic documents
- verify: unchanged(subject="epic documents", except_fields=[])
- returns: returns `ok`, the authored milestone path, whether it was reused, and newline-separated errors
- verify: json_path(path="$.ok", equals=True)
- code: `workflows/src/workhorse_workflows/author/milestone/nodes/milestone.py::validate_milestone`
