---
type: concept
slug: story-split-input-fields
title: Story-split input fields
---
# Story-split input fields

Every story-split run supplies both inputs; neither is an alternative implementation of the
other. `epic` identifies the one epic that the flow may split and review, while `operator_mode`
selects how that run handles a blocked decision. The flow rejects an empty `epic` and independently
rejects a mode other than `auto` or `human`, so there is no ranking between the fields.

Use `epic` to name the work under review. Choose `auto` when blocked work may receive up to two
automatic resolution attempts; choose `human` when it must await operator input immediately. Both
choices retain the selected epic and neither changes the story-split scope.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow`
- rule: provide a non-empty `epic` for every run, then choose `operator_mode` as `auto` for bounded automatic resolution or `human` for immediate operator escalation
- detail: [story-split flow inputs](story-split-flow-inputs.md)
- detail: [story-split flow concept selection](story-split-flow-concept-selection.md)
