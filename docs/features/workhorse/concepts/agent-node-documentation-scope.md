---
type: concept
slug: agent-node-documentation-scope
title: Agent node documentation scope
---
# Agent node documentation scope

`AgentNode` in `workhorse/workhorse/runner/spec.py::AgentNode` is one Pydantic configuration
record: its declaration contains the required identity and prompt fields together with the
optional execution, model-capacity, repository-access, telemetry, and control-flow settings.

Read [Agent node specification](agent-node-spec.md) first to understand that complete record
contract, including each field's type, default, and semantics. Read [Agent node field
selection](agent-node-field-selection.md) when choosing the field for a particular turn
configuration concern. Field selection is a companion to the record contract, not an alternative
`AgentNode` representation; compatible settings may be combined on the same node.

- rule: use the agent-node specification for the complete record contract and field selection only to choose the setting for a specific configuration concern; neither concept replaces the other
- prefers: [Agent node specification](agent-node-spec.md)
