---
type: concept
slug: agent-resilience-tuning
title: Agent resilience tuning
---
# Agent resilience tuning

`AgentResilience` settings are bounds for distinct stages of one recovery ladder, not alternative
implementations of the same delay or retry policy. Select the field that names the stage being
bounded: output parsing, transient invocation, context compaction, prompt reframing, executable
replacement, provider-cap waiting, turn timeout, or telemetry. Within a stage, the attempt count,
initial delay, single-delay ceiling, cumulative wait budget, and reporting cadence have separate
roles and are used together rather than chosen in place of one another.

Provider-cap settings are specific to the capped-turn wait: `cap_default_wait_s` applies when the
provider gives no reset time; `cap_wait_margin_s` is added to a reported reset; `cap_probe_s`
limits a sleep before rechecking an early reset; `cap_max_wait_s`, `cap_wait_budget_s`, and
`max_cap_waits` separately bound one wait, cumulative waiting, and consecutive waits; and
`cap_tick_s` controls progress notices. A zero probe interval deliberately selects the pre-probe
single wait through the reported reset. The transient-invocation and executable-replacement
backoffs each use their own count, base, cap, and cumulative budget. No source-level preference
or deprecation ranks these settings across stages.

- code: `workhorse/workhorse/config_run.py::AgentResilience`
- rule: choose the field for the recovery stage and bound it represents; do not substitute a field from another stage
- detail: [agent resilience concept selection](agent-resilience-concept-selection.md)
- detail: [agent resilience documentation selection](agent-resilience-documentation-selection.md)
