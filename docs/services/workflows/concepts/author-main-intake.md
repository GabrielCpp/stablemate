---
type: concept
slug: author-main-intake
title: Author main intake
---
# Author main intake

The intake nodes prepare and close the durable inputs used by the Author main flow. Epic mode
checks that the approved milestone lists epics and then advances that milestone only after
finalization. Story mode takes its input from the [debt register](../../ostler/concepts/the-debt-register.md)
and needs no intake node. The [story promotion](promote-a-record.md) picks one open record and
seeds its story. The nodes resolve the consuming repository from the explicit `repo_dir` input using
the survey resolver.

- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::validate_milestone_epics` @cbdf7f3f88f8
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::mark_milestone_authored` @cbdf7f3f88f8
- detail: [author milestone intake](../flows/author-milestone-intake.md)

## Methods

### validate_milestone_epics
- sig: `validate_milestone_epics(logger: logging.Logger, milestone: str, repo_dir: str = "") -> Defects`
- does: selects the milestone whose docs-root-relative path equals the supplied path
- verify: count(subject="milestones matching the path", equals=1)
- does: rejects the path when no milestone matches it
- verify: json_path(path="$.ok", equals=false)
- does: rejects the matching milestone when its `epics` collection is empty
- returns: `Defects(ok=true, errors="")` when the milestone lists at least one epic
- verify: json_path(path="$.ok", equals=true)
- returns: `Defects(ok=false, errors=...)` with one line per validation failure otherwise
- verify: json_path(path="$.errors", equals="example errors")
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::validate_milestone_epics` @cbdf7f3f88f8
- tests: `workflows/tests/author/test_config.py::test_a_milestone_must_list_at_least_one_epic`
- tests: `workflows/tests/author/test_config.py::test_epic_validation_ignores_other_milestones`

### mark_milestone_authored
- sig: `mark_milestone_authored(logger: logging.Logger, milestone: str, repo_dir: str = "") -> MilestoneStatus`
- does: reads the milestone document and returns its current status without writing when it is already `authored`
- verify: unchanged(subject="already-authored milestone", except_fields=[])
- does: changes only the first frontmatter `status` field from `approved` to `authored`
- verify: json_path(path="$.status", equals="authored")
- does: preserves the milestone body while writing the authored status
- verify: unchanged(subject="milestone body", except_fields=["status"])
- raises: `WorkflowFailed` when the milestone status is not `approved` or its frontmatter/status field is malformed
- verify: absent(subject="milestone status mutation after invalid status")
- returns: `MilestoneStatus` containing the milestone path and status `authored`
- code: `workflows/src/workhorse_workflows/author/finalize/nodes/milestone.py::mark_milestone_authored` @cbdf7f3f88f8
- tests: `workflows/tests/author/test_config.py::test_mark_milestone_authored_preserves_the_contract_body`
- tests: `workflows/tests/author/test_config.py::test_marking_an_authored_milestone_is_a_no_op`
- tests: `workflows/tests/author/test_config.py::test_marking_any_other_status_raises`
