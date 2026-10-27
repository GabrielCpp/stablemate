---
type: format
slug: coder-dev-plan-prompt
title: Coder dev-plan prompt
---
# Coder dev-plan prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-plan.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.plan` @9cb81c5987ec
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder dev phase turns](../concepts/coder-dev-phase-turns.md)
- detail: [coder development plan result](dev-plan-result.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_fresh_story_runs_plan_build_and_review_in_that_order`

The dev-plan envelope is the plan phase of the dev owner's story, on the strongest model. It tells
the agent to read the story, its epic, the repo's instructions and the docs nodes the story cites,
and to make every design call the story leaves open. A plan already in the spec directory that
still covers every Acceptance Criterion is kept. A plan that lacks a criterion is amended for that
criterion only. The turn writes the plan files through `ostler create spec`, commits them under the
story's footers, writes no product code, and ends with a `PlanResult`.

`plan.md` carries these sections:

- an Approach,
- the Changes in build order,
- Stages, for a story too big for one sitting,
- Testability,
- a Blast Radius, when a changed symbol has callers,
- Test Scenarios a parser reads,
- an empty Acceptance Walk heading the build fills,
- the Verification Commands copied from each layer's instruction files.

A multi-service story adds one plan file per service, named in that service's `plan_file`. The
envelope lists the services each repo declares. When no repo declares any, it tells the agent to
derive them from the layout.

## Fields

### story_path
- type: string path
- required: true
- semantics: authored story document that is the only target of the turn
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")

### spec_dir
- type: string path
- required: true
- semantics: directory receiving the plan files
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")

### services
- type: string
- default: empty string
- required: false
- semantics: the services each workspace repo declares, rendered as markdown, or empty when no repo declares any
- verify: json_path(path="$.services", equals="example services")

### brief_path
- type: string path
- required: true
- semantics: the file the rendered brief is kept at, so a later turn can read it again
- verify: json_path(path="$.brief_path", matches=".+/briefs/.+/plan\\.md$")

### operator_context
- type: string
- default: empty string
- required: false
- semantics: an operator answer to a plan block, treated as ground truth
- verify: json_path(path="$.operator_context", equals="Applied the change.")
