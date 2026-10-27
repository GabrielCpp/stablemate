---
type: format
slug: dev-story-result
title: Coder development story result
---
# Coder development story result

The dev owner replies with this readiness claim at the end of each review-phase turn. It carries the plan fields the story needs, so the run can write them without re-parsing agent-authored files. It also lists the findings the owner's reviewer raised and every question the owner put to the advisor before a decline.

- file: none — agent reply and checkpoint value
- config: `DevResult` dev owner output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult` @6f33cd53830e
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)
- detail: [coder dev-review prompt](coder-dev-review-prompt.md)

## Fields

### status
- type: literal `ready` or `blocked`
- required: true
- semantics: `ready` when the story is reviewed, every finding is answered, and every declared gate ran green in the last pass, `blocked` when only the operator can decide
- verify: json_path(path="$.status", matches="ready|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.status` @6f33cd53830e

### notes
- type: `str`
- default: empty string
- required: false
- semantics: what the owner built and ran green, or on `blocked` the one question that would unblock it
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.notes` @6f33cd53830e

### follow_ups
- type: list of follow-up entries, each with `title`, `reason`, `repo`, `area`, `pattern` and `symbols`
- default: empty list
- required: false
- semantics: product work the working slice does not need, filed as `coder` records on the debt register instead of done on the side
- verify: json_path(path="$.follow_ups", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.follow_ups` @6f33cd53830e
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::FollowUp` @6f33cd53830e
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)

Each follow-up entry carries six keys. `title` says what the work is in one line a person can act
on. `reason` says why the slice works without it and what it would improve. `repo` names the
workspace repository the work sits in, and it may be empty only when the run has one repository.
`area` is the module or service area as one lowercase kebab word, and it is required. A result
whose `area` is anything else, such as a file path, fails validation, so the agent corrects it in
the same turn instead of the register refusing the record at filing. The files go in `symbols`.
`pattern` is the kind of fix as a short lowercase kebab phrase, and it is required. `symbols` lists
the files or symbols the work touches and defaults to empty.

### findings
- type: list of review findings
- default: empty list
- required: false
- semantics: every finding the owner's reviewer reported this turn, verbatim and in order, before triage drops any, never a finding filed before the turn, empty on a turn that ran no review
- verify: json_path(path="$.findings", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.findings` @6f33cd53830e

### consults
- type: list of consult entries, each with `finding`, `question` and `advice`
- default: empty list
- required: false
- semantics: every question the owner put to the advisor before declining a finding, empty when no advisor is offered or nothing was declined
- verify: json_path(path="$.consults", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.consults` @6f33cd53830e
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::Consult` @6f33cd53830e
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_no_consult_is_reopened_and_named_when_an_advisor_is_offered`
- tests: `workflows/tests/coder/dev/test_flow.py::test_a_decline_with_a_consult_on_file_stays_declined`

Each consult entry carries three keys. `finding` is the finding's id as the answer file heads it.
`question` is the question the owner asked, in one line. `advice` is the advisor's answer as
given, and why the owner did not follow it if it did not. The flow records each consult beside
the work list. When an advisor is offered, the settlement reopens a decline with no consult on
file.
