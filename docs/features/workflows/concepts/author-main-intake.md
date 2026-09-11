---
type: concept
slug: author-main-intake
title: Author main intake
---
# Author main intake

The intake nodes prepare and close the durable inputs used by the Author main flow. Story mode
adopts unnamed backlog bullets before selecting one; epic mode validates the single milestone
owned by its roadmap and then advances that roadmap only after finalization. The nodes resolve the
consuming repository from the explicit `repo_dir` input using the survey resolver.

- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::adopt_backlog`
- detail: [author roadmap intake](../flows/author-roadmap-intake.md)

## Methods

### adopt_backlog
- sig: `adopt_backlog(logger: logging.Logger, repo_dir: str = "") -> Result`
- does: assigns Ostler ids to every unnamed backlog bullet before story selection or decomposition
- verify: persists(subject="adopted backlog identities")
- raises: `WorkflowFailed` with Ostler's failure message when backlog adoption is unsuccessful
- verify: absent(subject="backlog adoption result after failure")
- returns: the Ostler adoption result after logging its message
- verify: count(subject="backlog adoption results", equals=1)
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::adopt_backlog`
- code: `workflows/tests/author/test_workflow.py::backlogged`
- code: `workflows/tests/author/test_workflow.py::with_epic`
- code: `workflows/tests/author/test_workflow.py::test_story_mode_authors_one_bullet_and_does_not_commit`
- tests: `workflows/tests/author/test_workflow.py::test_story_mode_authors_one_bullet_and_does_not_commit`

### validate_roadmap_milestone
- sig: `validate_roadmap_milestone(logger: logging.Logger, roadmap: str, repo_dir: str = "") -> Defects`
- does: selects milestones whose `sourceItems` contains the supplied roadmap path
- verify: count(subject="milestones matching the roadmap", equals=1)
- does: rejects a roadmap unless exactly one matching milestone lists only that roadmap in `sourceItems`
- verify: json_path(path="$.ok", equals=false)
- does: rejects the matching milestone when its `epics` collection is empty
- verify: json_path(path="$.ok", equals=false)
- returns: `Defects(ok=true, errors="")` when the roadmap has exactly one non-empty owning milestone
- verify: json_path(path="$.ok", equals=true)
- returns: `Defects(ok=false, errors=...)` with one line per validation failure otherwise
- verify: json_path(path="$.errors", matches=".+")
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::validate_roadmap_milestone`
- tests: `workflows/tests/author/test_config.py::test_roadmap_must_source_exactly_one_nonempty_milestone`
- tests: `workflows/tests/author/test_config.py::test_roadmap_validation_ignores_unrelated_planning_defects`

### mark_roadmap_authored
- sig: `mark_roadmap_authored(logger: logging.Logger, roadmap: str, repo_dir: str = "") -> RoadmapStatus`
- does: reads the roadmap document and returns its current status without writing when it is already `authored`
- verify: unchanged(subject="already-authored roadmap", except_fields=[])
- does: changes only the first frontmatter `status` field from `approved` to `authored`
- verify: json_path(path="$.status", equals="authored")
- does: preserves the roadmap body while writing the authored status
- verify: unchanged(subject="roadmap body", except_fields=["status"])
- raises: `WorkflowFailed` when the roadmap status is not `approved` or its frontmatter/status field is malformed
- verify: absent(subject="roadmap status mutation after invalid status")
- returns: `RoadmapStatus` containing the roadmap path and status `authored`
- verify: json_path(path="$.status", equals="authored")
- code: `workflows/src/workhorse_workflows/author/main/nodes/intake.py::mark_roadmap_authored`
- tests: `workflows/tests/author/test_config.py::test_mark_roadmap_authored_preserves_the_contract_body`
