---
type: concept
slug: artifact-derived-author-stage-selection
title: Artifact-derived author stage selection
---
# Artifact-derived author stage selection

The Author main loop chooses its next unit from the approved milestone's current persisted epic,
story, and receipt artifacts. It does not use a fixed stage list or remember a previous choice.
The returned [AuthorStep](../workhorse-author.md#plan-and-dispatch) identifies exactly one
stage and its milestone/epic/story context.

- code: `workflows/src/workhorse_workflows/author/main/nodes/planner.py::plan_author_step` @0e64d8b59cbb
- rule: start at the epic split while the milestone lists no valid ordered epics, then complete epic documentation and seeds, then the reviewed story graph, then select the first uncompleted story in milestone epic order and story DAG order; finalize only when every current artifact passes
- tests: `workflows/tests/author/test_planner.py::test_first_undocumented_epic_uses_milestone_order`
- tests: `workflows/tests/author/test_planner.py::test_first_invalid_story_graph_uses_milestone_order`

The planner normalizes milestone epic names before validating uniqueness and existence. A missing,
duplicated, or reordered epic list on the milestone returns
`kind: epic-split` rather than selecting downstream work. Each queued epic must have an epic
document and at least one researched seed before story work is considered. A story graph must have
unique slugs, local dependencies, local seed coverage, a document for every story, and no cycle;
active seeds must also be covered. The separate story-split receipt must be passed and digest-current
before a graph can proceed to authoring.

An incomplete story is selected in dependency order. A story is considered current only when its
audit receipt says `passed` and its recorded SHA-256 digest matches the story bytes; missing,
malformed, stale, or changed receipts send that story back to authoring. The caller's blocked
`epic/story` keys are skipped for the remainder of the run, allowing later stories to proceed.
