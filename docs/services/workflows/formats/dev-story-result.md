---
type: format
slug: dev-story-result
title: Coder development story result
---
# Coder development story result

The dev owner replies with this readiness claim after each pass over its story. It carries the plan fields the story needs, so the run can write them without re-parsing agent-authored files.

- file: none — agent reply and checkpoint value
- config: `DevResult` dev owner output contract
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult` @0a54132ab719
- detail: [coder development schema contracts](../concepts/coder-dev-schema-contracts.md)
- detail: [coder development story prompt](coder-dev-story-prompt.md)

## Fields

### status
- type: literal `ready` or `blocked`
- required: true
- semantics: `ready` when the story is built and every declared gate ran green in the last pass, `blocked` when only the operator can decide
- verify: json_path(path="$.status", matches="ready|blocked")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.status` @0a54132ab719

### notes
- type: `str`
- default: empty string
- required: false
- semantics: what the owner built and ran green, or on `blocked` the one question that would unblock it
- verify: json_path(path="$.notes", equals="Applied the change and ran the gates.")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.notes` @0a54132ab719

### follow_ups
- type: list of follow-up entries, each with `title` and `reason`
- default: empty list
- required: false
- semantics: improvements the working slice does not need, filed to the backlog's deferred section instead of done on the side
- verify: json_path(path="$.follow_ups", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.follow_ups` @0a54132ab719
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::FollowUp` @0a54132ab719

### findings
- type: list of review findings
- default: empty list
- required: false
- semantics: every finding the owner's reviewer reported this turn, verbatim and in order, before triage drops any
- verify: json_path(path="$.findings", matches="^\\[.*\\]$")
- code: `workflows/src/workhorse_workflows/coder/shared/schemas/dev_story.py::DevResult.findings` @0a54132ab719
