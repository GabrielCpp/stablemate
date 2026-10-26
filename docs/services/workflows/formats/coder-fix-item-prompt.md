---
type: format
slug: coder-fix-item-prompt
title: Coder fix-item prompt
---
# Coder fix-item prompt

- file: `workflows/src/workhorse_workflows/coder/fix/prompts/fix-item.md`
- code: `workflows/src/workhorse_workflows/coder/fix/flow.py::Fix.work` @670e5cb59adb
- detail: [coder standalone fix flow](../flows/coder-fix.md)
- detail: [coder dev-story prompt](coder-dev-story-prompt.md)
- tests: `workflows/tests/coder/fix/test_flow.py::test_the_first_pass_is_handed_the_item_and_no_report_at_all`
- tests: `workflows/tests/coder/shared/test_roles.py::test_every_prompt_renders_with_its_partials`

The fix-item envelope makes the agent the owner of one drained register record, seeded as a
one-criterion story. The owner has a fixer repair the item, has a fresh QA checker exercise the
change and write `qa.md` in the spec directory, has a triager sort what QA found, and sends the
real defects back to fixers until QA passes. The turn ends with the repair committed in every
repository it changed, the gates green and an `ImplResult`. The envelope adds a section when the
workflow supplies a failed-check report or an operator answer.

The item itself is the first finding, and its fixer follows the same rule as the fixers of QA's
findings. The dev-story envelope gives its fixers this rule too, from the same shared text, so
the two lanes cannot drift apart:

- A finding that reports wrong behaviour stays a defect until a test says otherwise. A "not a
  defect" verdict on one cites a passing test that drives the finding's own case.
- Each fixer loads the `isolating-causes` and `root-cause` skills when the repository installs
  both. The sentence is absent from the prompt otherwise.
- A fixer turns the finding into a failing test first, then runs every case the criterion's
  clause covers, not only the reported one.
- Before the edit, a fixer writes the why-chain: why the fix is needed, the decision that caused
  it, and how that decision could have been prevented, until the answer is the property the
  criterion states.
- A branch, a count or a check for the reported case alone is handling, not a fix.
- Findings whose chains meet are one fix.
- Each fix lands at its cause with the test that covers it, as its own commit with its chain in
  the commit body.

## Fields

### item_text
- type: string
- required: true
- semantics: the summary of the drained `qa` record that is the only item this turn repairs
- verify: json_path(path="$.item_text", equals="Clear the cache on sign-out")

### story_path
- type: string path
- required: true
- semantics: the one-criterion story seeded from the record
- verify: json_path(path="$.story_path", equals="docs/stories/acme-story/story.md")

### spec_dir
- type: string path
- required: true
- semantics: directory holding the turn's plan and the QA checker's `qa.md`
- verify: json_path(path="$.spec_dir", equals="docs/stories/acme-story")

### qa_dir
- type: string path
- required: true
- semantics: the story's QA directory
- verify: json_path(path="$.qa_dir", equals="docs/stories/acme-story/qa")

### target_env
- type: string
- default: `local`
- required: true
- semantics: the environment the repair and its QA run against
- verify: json_path(path="$.target_env", equals="local")

### report
- type: string
- default: empty string
- required: false
- semantics: the failed-gate report this turn repairs, from the previous lap's checks
- verify: json_path(path="$.report", equals="example report")

### operator_context
- type: string
- default: empty string
- required: false
- semantics: an operator answer treated as ground truth that overrides earlier assumptions
- verify: json_path(path="$.operator_context", equals="Applied the change.")
