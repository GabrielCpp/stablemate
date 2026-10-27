---
type: format
slug: coder-dev-follow-up-prompt
title: Coder dev follow-up prompt
---
# Coder dev follow-up prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-follow-up.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev._turn` @9cb81c5987ec
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder dev phase turns](../concepts/coder-dev-phase-turns.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`

The follow-up note is the turn the flow sends instead of a phase's brief when that phase already
ran on the story's current conversation. It names the phase and the story. It says the brief
still governs the turn, and it names the file the brief is kept at, so an agent that lost the
brief to a compaction reads it again. It carries only what changed since the last turn: the
report that sent the turn back, QA's findings, the other open findings, the review prefix, the
operator answer and the task note. It asks for the JSON result the brief describes. A review
follow-up also asks the agent to re-state the plan's full structure, because the review result
replaces the last one.

## Fields

### phase
- type: literal `plan`, `build` or `review`
- required: true
- semantics: the phase the note continues
- verify: json_path(path="$.phase", matches="plan|build|review")
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`

### story_id
- type: string
- required: true
- semantics: the id of the story the phase works
- verify: json_path(path="$.story_id", equals="acme-story")

### brief_path
- type: string path
- required: true
- semantics: the file the phase's brief is kept at
- verify: json_path(path="$.brief_path", matches=".+/briefs/.+\\.md$")
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`

### report
- type: string
- default: empty string
- required: false
- semantics: the report that sent the turn back
- verify: json_path(path="$.report", equals="example report")
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`

### qa_findings
- type: string
- default: empty string
- required: false
- semantics: the open findings QA filed against the work item
- verify: json_path(path="$.qa_findings", equals="example qa findings")

### findings
- type: string
- default: empty string
- required: false
- semantics: the other open findings, each of which needs a section in the answer file
- verify: json_path(path="$.findings", equals="example findings")

### review_prefix
- type: string
- default: empty string
- required: false
- semantics: the id prefix a new review in this turn files its findings under, empty outside the review phase
- verify: json_path(path="$.review_prefix", matches="^(.+/review-[0-9]+\\.)?$")

### operator_context
- type: string
- default: empty string
- required: false
- semantics: an operator answer to a block, treated as ground truth
- verify: json_path(path="$.operator_context", equals="Applied the change.")

### note
- type: string
- default: empty string
- required: false
- semantics: the workflow's instruction for this turn, such as a rescope note from QA
- verify: json_path(path="$.note", equals="example note")
