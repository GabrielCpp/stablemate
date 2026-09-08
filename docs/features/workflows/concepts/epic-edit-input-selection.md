---
type: concept
slug: epic-edit-input-selection
title: Epic edit input selection
---
# Epic edit input selection

`EpicEdit` has two input contexts rather than competing fields. A direct invocation supplies an
epic identifier and requested change, with `force` authorizing permitted removals. A story-edit
handoff supplies the validated `intent` instead. `EpicEdit.start` first selects a handoff intent
whose epic is set; only when it is absent does it require the direct inputs and construct an
intent from them. `operator_mode` is workflow-runtime routing metadata in either context, not an
edit request.

For the choice between direct and handoff entry contexts, see [epic edit invocation
selection](epic-edit-invocation-selection.md).

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- rule: supply `intent` for a story-edit handoff; otherwise supply `epic` and `change`, optionally with `force`; treat `operator_mode` as runtime routing metadata
- detail: [epic edit concept selection](epic-edit-concept-selection.md)
