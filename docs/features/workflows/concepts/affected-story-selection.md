---
type: concept
slug: affected-story-selection
title: Affected story selection
---
# Affected story selection

`select_affected_story` is the direct selection boundary: it resolves only the story at the
current approved-list index, returns the exhausted-list result when that index is past the end,
and rejects a listed story that is no longer present. `EpicEdit.next_affected_story` consumes that
result to choose coverage for an exhausted list or mockup design for the selected story.

Use the method node for the callable's return, exhaustion, and missing-story contract. Use the
flow phase for its place in the ordered authoring journey and the work that follows selection.
Neither view supersedes the other; they document the same selection at different scopes.

- code: `workflows/src/workhorse_workflows/author/epic_edit/nodes/edit.py::select_affected_story`
- rule: use the method contract for one indexed selection and the flow phase for orchestration of the approved affected-story list
