---
type: concept
slug: epic-edit-documentation-selection
title: Epic edit documentation selection
---
# Epic edit documentation selection

These concepts describe the same `EpicEdit` workflow from complementary entry points, not
alternative implementations. Read [author epic edit subflow](author-epic-edit-subflow.md) for the
full reconciliation lifecycle, [epic edit input selection](epic-edit-input-selection.md) when
binding fields to the workflow, and [epic edit invocation selection](epic-edit-invocation-selection.md)
when choosing between a story-edit handoff and a direct request.

`EpicEdit.start` keeps the contexts distinct: it uses a handoff `intent` with an epic already set,
or otherwise requires direct `epic` and `change` values before constructing an `EditIntent`. No
document is preferred or deprecated because each answers a different reader question about that
single machine.

- code: `workflows/src/workhorse_workflows/author/epic_edit/flow.py::EpicEdit`
- rule: select the document by whether the reader needs the workflow lifecycle, input binding, or invocation context; they describe one `EpicEdit` machine
- detail: [epic edit concept selection](epic-edit-concept-selection.md)
