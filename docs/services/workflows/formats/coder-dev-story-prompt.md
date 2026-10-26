---
type: format
slug: coder-dev-story-prompt
title: Coder dev-story prompt
---
# Coder dev-story prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-story.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.build` @6b4e303557ef
- detail: [coder development flow](../flows/coder-dev.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_clean_pass_settles_the_fix_and_records_the_decline`

The dev-story envelope makes the agent the owner of one story. It tells the agent to plan the
supplied story, build it through subagents sized to each task, have a fresh reviewer judge the
diff, triage and fix the findings, and answer every finding in the answer file. The turn ends with
the plan files in the spec directory, the code committed under the story's footers, every gate
green and a `DevResult`. The envelope adds a section when the workflow supplies a follow-up, a
rescope note, a failed-check report, open findings or an operator answer.

Its fixers follow the root-cause rule the
[coder fix-item prompt](coder-fix-item-prompt.md) lists, rendered from the same shared text. One
fix for several findings is answered under each of their ids.

A "not a defect" decline opens its reason with those words and names, as a `- test:` bullet, the
test that drives the finding's own case. The settlement rejects one that names no such test.

## Fields

### story_path
- type: string path
- required: true
- semantics: authored story document that is the only target of the turn
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")

### story_services
- type: list of book names
- required: false
- semantics: the `services` of the story, rendered as a line naming the books under `docs/services/` the story changes
- verify: count(subject="story_services", equals=2)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_clean_pass_settles_the_fix_and_records_the_decline`

### spec_dir
- type: string path
- required: true
- semantics: directory receiving the plan files
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")

### review_prefix
- type: string
- required: true
- semantics: the id prefix under which the run files this turn's nth review finding
- verify: json_path(path="$.review_prefix", matches=".+/review-[0-9]+\\.")

### report
- type: string
- default: empty string
- required: false
- semantics: the failed-check report this turn repairs, with no new review
- verify: json_path(path="$.report", equals="example report")

### findings
- type: string
- default: empty string
- required: false
- semantics: the open findings, each of which needs a section in the answer file
- verify: json_path(path="$.findings", equals="example findings")

### operator_context
- type: string
- default: empty string
- required: false
- semantics: an operator answer treated as ground truth that overrides earlier assumptions
- verify: json_path(path="$.operator_context", equals="Applied the change.")
