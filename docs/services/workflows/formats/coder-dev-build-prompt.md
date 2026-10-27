---
type: format
slug: coder-dev-build-prompt
title: Coder dev-build prompt
---
# Coder dev-build prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-build.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.build` @9cb81c5987ec
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder dev phase turns](../concepts/coder-dev-phase-turns.md)
- detail: [coder development build result](dev-build-result.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_fresh_story_runs_plan_build_and_review_in_that_order`
- tests: `workflows/tests/coder/dev/test_flow.py::test_an_operator_answer_on_a_build_block_returns_to_build`

The dev-build envelope is the build phase of the dev owner's story, on the conversation the plan
ran on. It tells the agent to read the plan, build each change with its test, and run every gate
and verification command the plan declares. It then brings each touched layer up once and writes
one Acceptance Walk entry per criterion from what it saw hold. The turn commits under the story's
footers and ends with a `BuildResult`. The agent builds the story itself. It hands a lookup or a
bounded unit to a subagent only where that saves work.

A departure is any change the build makes to the plan. The envelope allows one only when building
the plan as written would fail a criterion or a gate. It asks for each departure in `plan.md` and
in the result. When the turn is offered an `advisor` delegate, the envelope asks the agent to
consult it before each departure and to copy its answer into the departure's `advice`. The flow
sends a departure with no advice back to the build.

## Fields

### story_path
- type: string path
- required: true
- semantics: authored story document that is the only target of the turn
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")

### spec_dir
- type: string path
- required: true
- semantics: directory holding the plan files the build follows
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")

### report
- type: string
- default: empty string
- required: false
- semantics: the report that sent the build back, naming each departure that carries no advice
- verify: json_path(path="$.report", equals="example report")
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_departure_without_advice_sends_the_build_back_when_an_advisor_is_offered`

### advisor
- type: boolean
- default: false
- required: false
- semantics: whether the turn is offered an `advisor` delegate, which adds the consult-before-departing paragraph
- verify: json_path(path="$.advisor", equals=true)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_departure_without_advice_sends_the_build_back_when_an_advisor_is_offered`

### brief_path
- type: string path
- required: true
- semantics: the file the rendered brief is kept at, so a later turn can read it again
- verify: json_path(path="$.brief_path", matches=".+/briefs/.+/build\\.md$")

### operator_context
- type: string
- default: empty string
- required: false
- semantics: an operator answer to a build block, treated as ground truth
- verify: json_path(path="$.operator_context", equals="Applied the change.")
