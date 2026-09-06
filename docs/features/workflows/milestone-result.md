---
type: format
slug: milestone-result
title: Milestone result
---
# Milestone result

The agent's machine-readable reply for the milestone authoring turn. `complete` means the
milestone was created or reused; `blocked` carries a question or other reason that is presented
through the operator-awaiting path.

- file: none — in-memory Pydantic model
- config: none
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneResult`
- detail: [author milestone subflow](concepts/author-milestone-subflow.md)
- tests: `workflows/tests/author/milestone/test_flow.py::_Agent.__call__`

## Fields

### status
- type: `Literal["complete", "blocked"]`
- default: no default
- required: true
- semantics: selects successful milestone authoring or operator blocking
- verify: json_path(path="$.status", equals="complete")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneResult`

### notes
- type: string
- default: no default
- required: true
- semantics: describes the created or reused milestone, or explains the blocking question
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/schemas.py::MilestoneResult`
