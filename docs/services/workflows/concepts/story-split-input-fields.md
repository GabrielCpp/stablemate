---
type: concept
slug: story-split-input-fields
title: Story-split input fields
---
# Story-split input fields

Every story-split run supplies `epic` and may supply `note`. Neither is an alternative
implementation of the other. `epic` identifies the one epic that the flow may split and review.
`note` carries context from an earlier attempt, such as the operator's answer after a blocked
split, and the splitter reads it before it works. The flow rejects an empty `epic`.

Use `epic` to name the work under review. Leave `note` empty on a first attempt. Both choices
retain the selected epic and neither changes the story-split scope.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow` @9e26ab4671cb
- rule: provide a non-empty `epic` for every run, and a `note` only when an earlier attempt left an answer to carry
- detail: [story-split flow inputs](story-split-flow-inputs.md)
- detail: [story-split flow concept selection](story-split-flow-concept-selection.md)
