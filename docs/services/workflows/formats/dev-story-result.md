---
type: format
slug: dev-story-result
title: Coder development story result
---
# Coder development story result

The dev owner replies with this readiness claim after each pass over its story. It carries the plan fields the story needs, so the run can write them without re-parsing agent-authored files.

- file: none — agent reply and checkpoint value
- config: `DevResult` dev owner output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult` @9fc435ce5241
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)
- detail: [coder development story prompt](coder-dev-story-prompt.md)

## Fields

### status
- type: literal `ready` or `blocked`
- required: true
- semantics: `ready` when the story is built and every declared gate ran green in the last pass, `blocked` when only the operator can decide
- verify: json_path(path="$.status", matches="ready|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.status` @9fc435ce5241

### notes
- type: `str`
- default: empty string
- required: false
- semantics: what the owner built and ran green, or on `blocked` the one question that would unblock it
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.notes` @9fc435ce5241

### follow_ups
- type: list of follow-up entries, each with `title`, `reason`, `repo`, `area`, `pattern` and `symbols`
- default: empty list
- required: false
- semantics: product work the working slice does not need, filed as `coder` records on the debt register instead of done on the side
- verify: json_path(path="$.follow_ups", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.follow_ups` @9fc435ce5241
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::FollowUp` @9fc435ce5241
- detail: [coder backlog contract](../concepts/coder-backlog-contract.md)

Each follow-up entry carries six keys. `title` says what the work is in one line a person can act
on. `reason` says why the slice works without it and what it would improve. `repo` names the
workspace repository the work sits in, and it may be empty only when the run has one repository.
`area` is the module or service area as one lowercase kebab word, and it is required. `pattern`
is the kind of fix as a short lowercase kebab phrase, and it is required. `symbols` lists the
files or symbols the work touches and defaults to empty.

### findings
- type: list of review findings
- default: empty list
- required: false
- semantics: every finding the owner's reviewer reported this turn, verbatim and in order, before triage drops any
- verify: json_path(path="$.findings", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.findings` @9fc435ce5241
