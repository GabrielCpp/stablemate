---
type: concept
slug: story-split-flow-inputs
title: Story-split flow inputs
---
# Story-split flow inputs

`StorySplitFlow` requires both inputs because they govern independent decisions. `epic` names
the one epic to split and review; `operator_mode` governs how blocked decisions are handled
during that work. They are not alternative entry points, so neither concept supersedes or is
preferred over the other.

Every run supplies a non-empty `epic` and an `operator_mode` of `auto` or `human`. Use `auto`
when the flow may make up to two automatic resolution attempts before awaiting operator input;
use `human` when it must await that input as soon as work is blocked. The mode never changes
which epic is in scope.

- code: `workflows/src/workhorse_workflows/author/story_split/flow.py::StorySplitFlow`
- rule: provide both inputs; select `operator_mode` for blocked-decision handling, not as an alternative to the required `epic`
- detail: [story-split flow concept selection](story-split-flow-concept-selection.md)
