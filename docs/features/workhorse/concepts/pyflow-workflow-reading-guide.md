---
type: concept
slug: pyflow-workflow-reading-guide
title: Pyflow workflow reading guide
---
# Pyflow workflow reading guide

`Workflow` is one state-machine base class, not a set of interchangeable implementations.
Its source defines the run seams (`call`, `agent`, `handoff`, and `output`) alongside the
configuration and registration fields that govern input injection, span classification, state
discovery, and transition budgets.

Read [pyflow workflow API](pyflow-workflow-api.md) when implementing or reviewing lifecycle,
state, and seam behavior. Read [pyflow workflow field selection](pyflow-workflow-field-selection.md)
when setting subclass fields. Read [pyflow workflow concept selection](pyflow-workflow-concept-selection.md)
when deciding which of those complementary references answers the immediate question. Neither
reference supersedes the other because each describes a distinct part of
`workhorse/workhorse/pyflow/workflow.py::Workflow`.

- rule: choose the API reference for lifecycle, states, and run seams; choose the field-selection reference for subclass configuration and registration; use the concept-selection reference to distinguish those complementary reading contexts
