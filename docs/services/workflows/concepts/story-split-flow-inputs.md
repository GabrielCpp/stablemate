---
type: concept
slug: story-split-flow-inputs
title: Story-split flow inputs
---
# Story-split flow inputs

`StorySplitFlow` takes two inputs that govern independent decisions. `epic` names the one epic to
split and review, and it is required. `note` carries an earlier answer into the splitter's prompt,
and it is optional. They are not alternative entry points, so neither concept supersedes or is
preferred over the other.

Every run supplies a non-empty `epic`. The Author flow supplies a `note` when it retries a blocked
split with the operator's answer. The note never changes which epic is in scope. Blocked decisions
no longer depend on a mode: the PM answers the splitter's questions, and the operator is asked only
when the split stays blocked.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow` @9e26ab4671cb
- rule: provide `epic` always, and `note` only to carry an earlier answer
- detail: [story-split flow concept selection](story-split-flow-concept-selection.md)
