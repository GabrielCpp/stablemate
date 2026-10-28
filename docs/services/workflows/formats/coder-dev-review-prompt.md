---
type: format
slug: coder-dev-review-prompt
title: Coder dev-review prompt
---
# Coder dev-review prompt

- file: `workflows/src/workhorse_workflows/coder/dev/prompts/dev-review.md`
- code: `workflows/src/workhorse_workflows/coder/dev/flow.py::Dev.review` @80dd00949225
- detail: [coder development flow](../flows/coder-dev.md)
- detail: [coder dev phase turns](../concepts/coder-dev-phase-turns.md)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_clean_pass_settles_the_fix_and_records_the_decline`
- tests: `workflows/tests/coder/dev/test_flow.py::test_the_first_review_turn_writes_the_reviewer_files_beside_its_brief`
- tests: `workflows/tests/coder/test_status_line_ownership.py::test_a_primed_brief_points_at_the_opening_brief_instead`

The dev-review envelope is the review phase of the dev owner's story, on the conversation the
plan and the build ran on. It tells the agent to have a fresh reviewer judge the diff, triage
every finding the review and the run filed, fix the real ones at their cause, and answer each one
in the answer file. The turn ends with every finding answered, each fix committed with its test,
every gate green and a `DevResult`. Every repair lap the checks send back lands in this phase, and
a repair turn runs no new review. The envelope adds a section when the workflow supplies QA's
findings, other open findings, a failed-check report, a follow-up, a rescope note or an operator
answer. QA's findings carry the rule that a fix covers every case of the criterion it breaks, and
that the owner reopens its own earlier declines and tests on the same code.

When the turn is offered an `advisor` delegate, the envelope asks the owner to consult it before
each decline and to report each consult under the finding's id. The settlement reopens a decline
with no consult on file.

When the envelope opens the story's conversation, it carries the story's standing rules: the
coding standards and the run branch, the scope and when to block, the status line the turn leaves
alone, the commit footers, the services the story changes and the follow-up the run works. When an
earlier phase opened the conversation, the envelope names that phase's brief instead and repeats
none of them. A conversation the engine starts again opens with the full rules.

The envelope carries neither the reviewer's brief nor the answer file's format. The flow renders
each into its own file beside the review brief before the turn, and the envelope names both paths.
The owner tells each reviewer to read the reviewer's brief first, and reads the answer file's
format before it writes its answers. Each file is written once per conversation, with the review
brief itself.

Its fixers follow the root-cause rule the
[coder fix-item prompt](coder-fix-item-prompt.md) lists, rendered from the same shared text. One
fix for several findings is answered under each of their ids.

A "not a defect" decline opens its reason with those words and names, as a `- test:` bullet, the
test that drives the finding's own case. The settlement rejects one that names no such test.

The reviewer's Reuse lens searches the whole tree, not only the diff, for code the diff repeats:
by name, by behaviour and by signature. Its finding targets the added lines and names the code
they repeat. A Reuse finding is declined only as a coincidence. The reason opens with
`coincidence:` and gives two different reasons the copies change, separated by `;`. The
settlement rejects any other Reuse decline, an improvement the slice does not need included.

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
- semantics: the open findings no QA run filed, each of which needs a section in the answer file
- verify: json_path(path="$.findings", equals="example findings")

### qa_findings
- type: string
- default: empty string
- required: false
- semantics: the open findings QA filed against the work item, each a case where an Acceptance Criterion does not hold
- verify: json_path(path="$.qa_findings", equals="example qa findings")

### advisor
- type: boolean
- default: false
- required: false
- semantics: whether the turn is offered an `advisor` delegate, which adds the consult-before-decline section
- verify: json_path(path="$.advisor", equals=true)
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`

### brief_path
- type: string path
- required: true
- semantics: the file the rendered brief is kept at, so a later turn can read it again
- verify: json_path(path="$.brief_path", matches=".+/briefs/.+/review\\.md$")

### opening_brief
- type: string path
- default: empty string
- required: false
- semantics: the brief of the phase that opened the story's conversation, which carries the story's standing rules, or empty when this review turn opens the conversation and carries them itself
- verify: json_path(path="$.opening_brief", matches="^(.+/briefs/.+/[a-z]+\\.md)?$")

### reviewer_brief
- type: string path
- required: true
- semantics: the file beside the review brief that holds the reviewer's brief, rendered from `dev-reviewer.md` for this story: what to read, the six lenses, the score bar and the fields of a finding
- verify: json_path(path="$.reviewer_brief", matches=".+/briefs/.+/dev-reviewer\\.md$")

### answer_format
- type: string path
- required: true
- semantics: the file beside the review brief that holds the answer file's format, rendered from `dev-answer-file.md`: one section per finding, an example of each answer, and the checks the settlement runs
- verify: json_path(path="$.answer_format", matches=".+/briefs/.+/dev-answer-file\\.md$")
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_later_turn_of_a_phase_on_the_same_conversation_sends_only_the_follow_up_note`

### operator_context
- type: string
- default: empty string
- required: false
- semantics: an operator answer treated as ground truth that overrides earlier assumptions
- verify: json_path(path="$.operator_context", equals="Applied the change.")
