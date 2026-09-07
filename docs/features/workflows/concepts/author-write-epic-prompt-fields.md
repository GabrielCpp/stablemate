---
type: concept
slug: author-write-epic-prompt-fields
title: Author write-epic prompt fields
---
# Author write-epic prompt fields

The authoring call passes `epic`, `epic_dir`, `roadmap`, and `features_dir` to the write-epic
prompt as its caller-selected context. `status` and `notes` instead come from the
`WriteEpicResult` returned by that prompt: `status` controls whether the workflow gates or
validates the authored epic, and `notes` supplies the gate's explanation.

No field is a fallback or replacement for another. Select a field by the direction and purpose
of the value: provide the four context fields to request an authoring turn, then read the two
result fields to act on that turn's outcome.

- code: `workflows/src/workhorse_workflows/author/epic_author/flow.py::EpicAuthor.author_epic`
- rule: use input fields for caller context and result fields for the authoring outcome; no ranking exists within either group
