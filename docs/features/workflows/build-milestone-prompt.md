---
type: format
slug: build-milestone-prompt
title: Build milestone prompt
---
# Build milestone prompt

- file: `workflows/src/workhorse_workflows/author/milestone/prompts/build-milestone.md`
- config: none
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`
- detail: [author milestone subflow](concepts/author-milestone-subflow.md)
- tests: `workflows/tests/author/milestone/test_flow.py::_Agent.__call__`

This prompt gives one high-power agent turn responsibility for exactly one milestone owned by the
approved roadmap. The agent may create the milestone when it is absent or reuse the existing one,
but must preserve the ordered epic list and must not change epics, stories, seeds, branches,
commits, or downstream artifacts. The response is a JSON object accepted by
[milestone result](milestone-result.md).

## Fields

### roadmap
- type: string
- required: true
- semantics: repository-relative approved roadmap path that is the milestone's sole source item
- verify: json_path(path="$.roadmap", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`

### status
- type: `Literal["complete", "blocked"]`
- required: true
- semantics: reports whether the milestone was created or reused, or whether the turn needs an operator decision
- verify: json_path(path="$.status", matches="^(complete|blocked)$")
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`

### notes
- type: string
- required: true
- semantics: describes the created or reused milestone, or states the blocking question
- verify: json_path(path="$.notes", matches=".+")
- code: `workflows/src/workhorse_workflows/author/milestone/flow.py::Milestone.start`
