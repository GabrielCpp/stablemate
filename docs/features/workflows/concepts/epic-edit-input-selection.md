---
type: concept
slug: epic-edit-input-selection
title: Epic edit input selection
---
# Epic edit input selection

`EpicEdit` has two input contexts rather than competing fields. A direct invocation supplies an
epic identifier and requested change, with `force` authorizing permitted removals. A story-edit
handoff supplies the validated `intent` instead, so the direct inputs are not consulted when its
epic is set. `operator_mode` is workflow-runtime routing metadata in either context, not an edit
request. The source declares no ranking among these fields because each belongs to a different
part of that invocation contract.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- rule: supply `intent` for a story-edit handoff; otherwise supply `epic` and `change`, optionally with `force`; treat `operator_mode` as runtime routing metadata
