---
type: concept
slug: agent-resilience-documentation-selection
title: Agent resilience documentation selection
---
# Agent resilience documentation selection

`AgentResilience` and `RunConfig` are complementary views of one immutable per-run
configuration. `RunConfig.from_env` builds its `resilience` field with
`AgentResilience.from_env`, so resilience tuning describes the recovery policy itself
while per-run configuration describes the snapshot that carries it through a run.

Neither view is superseded. The source declares `AgentResilience` as the type of
`RunConfig.resilience` and constructs that field at the CLI boundary; choose the view
that answers the reader's question rather than treating either as a replacement for the
other.

- rule: use agent resilience tuning for recovery-stage settings, per-run configuration for the immutable run snapshot that carries the policy, and concept selection for the relationship between those views
