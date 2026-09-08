---
type: concept
slug: epic-edit-invocation-selection
title: Epic edit invocation selection
---
# Epic edit invocation selection

`EpicEdit` accepts either a story-edit handoff or a direct scope-change invocation. The contexts
are not interchangeable: a handoff has already supplied a validated `EditIntent`, while a direct
invocation must supply the epic identifier and requested change from which `EpicEdit` constructs
that intent. This preserves the handoff's selected epic and makes an incomplete direct request a
workflow failure instead of silently combining inputs from both contexts.

`operator_mode` accompanies either context only as workflow-runtime routing metadata. It does not
select an epic or describe the requested edit.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- rule: use a handoff `intent` when `intent.epic` is set; otherwise provide both direct `epic` and `change` inputs, with `force` only for permitted removals
- detail: [epic edit concept selection](epic-edit-concept-selection.md)
