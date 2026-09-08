---
type: concept
slug: step-field-selection
title: Step field selection
---
# Step field selection

A `Step` is the complete statically discovered unit of work in a workflow state. It retains
source order so a graph can render the state as a chain, while its attributes expose the kind of
engine seam, the target identified by that kind, and the optional human-readable caption.

Use [`Step`](pyflow-state-graph.md#field-step) when a consumer needs the complete unit or its
position among a state's work. Use [`Step.kind`](pyflow-state-graph.md#field-stepkind),
[`Step.name`](pyflow-state-graph.md#field-stepname), or
[`Step.summary`](pyflow-state-graph.md#field-stepsummary) when it needs only that attribute. The
fields are current views of the same record, not alternate implementations, so none supersedes
another.

- code: `workhorse/workhorse/pyflow/graph.py::Step`
- rule: use `Step` for a source-ordered work item; use `kind`, `name`, or `summary` only when that individual attribute is the required view
