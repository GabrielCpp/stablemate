---
type: concept
slug: agent-backend-documentation-scope
title: AgentBackend documentation scope
---
# AgentBackend documentation scope

`AgentBackend` in `workhorse/workhorse/runner/backends/__init__.py::AgentBackend` is one
port, not two implementations. Read [AgentBackend](agent-backend.md) when choosing or
using the uniform harness-backend contract, including its operations and runtime backend
selection. Read [AgentBackend attribute overrides](agent-backend-attribute-overrides.md)
when implementing a concrete CLI adapter and deciding which inherited class attributes it
must change for that CLI's capabilities.

The base class supplies the `name`, `default_model`, and `supports_compaction` defaults;
each adapter changes only the values that differ. The contract document is therefore the
starting point for every caller, while the attribute document is an implementation guide
for adapter authors rather than an alternative port.

- rule: use the AgentBackend contract for harness integration; use the attribute-overrides concept only when implementing a CLI adapter whose capabilities differ from the inherited defaults
- prefers: [AgentBackend](agent-backend.md)
