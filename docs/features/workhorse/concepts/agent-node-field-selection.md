---
type: concept
slug: agent-node-field-selection
title: Agent node field selection
---
# Agent node field selection

`AgentNode` is one configuration record, and its fields are complementary rather than competing
implementations. Select the field that governs the concern being configured: identity and prompt
input (`id`, `prompt`, and `args`), declared results (`outputs`), an operator-defined abstract
capacity tier (`power`), wall-clock execution limits (`timeout`), recovery after a failed turn
(`retries`) or a transient provider failure (`invoke_retries`), process location and repository access (`cwd` and
`add_dirs`), live telemetry (`activity`), or the following node (`next`). `type` identifies the
record as an agent node.

`power` accepts any tier name in the operator's configuration. The shipped workflows conventionally
use `low`, `medium`, `high`, `smart`, and `extra-smart`, from cheapest to most capable, but the
engine does not restrict the vocabulary; an unmapped or misspelled tier falls through to the active
backend's default. `timeout` bounds one turn in seconds and accepts an unbounded value; `retries`
controls fresh reframe attempts after a failed turn, while `invoke_retries` controls retries for
transient provider failures. No field replaces or ranks above another. A workflow may set any
compatible combination; omitted optional fields retain the defaults declared by the model.

- code: `workhorse/workhorse/runner/spec.py::AgentNode`
- rule: select the field for the distinct agent-turn concern being configured; the fields are complementary and have no ranking or replacement relationship
- detail: [Agent node documentation scope](agent-node-documentation-scope.md)
