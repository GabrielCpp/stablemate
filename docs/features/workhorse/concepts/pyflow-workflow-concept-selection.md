---
type: concept
slug: pyflow-workflow-concept-selection
title: Pyflow workflow concept selection
---
# Pyflow workflow concept selection

`Workflow` has one state-machine contract, documented from two complementary reading contexts.
Use [pyflow workflow API](pyflow-workflow-api.md) to understand the base class lifecycle,
state registration, and run seams. Use [pyflow workflow field selection](pyflow-workflow-field-selection.md)
when choosing a subclass configuration or registration field. The fields are distinct controls:
they do not replace one another, and neither document is a preferred implementation.

- code: `workhorse/workhorse/pyflow/workflow.py::Workflow`
- rule: use the API reference for `Workflow` lifecycle and seam behavior; use the field-selection reference when choosing its complementary fields, with no ranking or replacement relationship
- detail: [pyflow workflow reading guide](pyflow-workflow-reading-guide.md)
