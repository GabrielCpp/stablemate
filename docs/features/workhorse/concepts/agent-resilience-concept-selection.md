---
type: concept
slug: agent-resilience-concept-selection
title: Agent resilience concept selection
---
# Agent resilience concept selection

`AgentResilience` and `RunConfig` document different views of the same immutable
per-run policy. `AgentResilience` names the recovery-ladder limits and waits. `RunConfig`
captures that policy from the environment once at the CLI boundary and passes it through a
run; its `resilience` field is a default `AgentResilience` instance.

Use agent resilience tuning when choosing a setting for a recovery stage or one of that
stage's bounds. Use per-run configuration when determining how the policy is captured,
stored, and supplied alongside the rest of a run's immutable configuration. Neither view
supersedes the other: the source defines `AgentResilience` as a field of `RunConfig`, and
both remain current for their respective contexts.

- code: `workhorse/workhorse/config_run.py::AgentResilience`
- rule: use agent resilience tuning for recovery-stage settings and per-run configuration for the immutable run snapshot that contains them
- detail: [agent resilience documentation selection](agent-resilience-documentation-selection.md)
