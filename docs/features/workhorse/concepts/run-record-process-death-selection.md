---
type: concept
slug: run-record-process-death-selection
title: Run record process-death field selection
---
# Run record process-death field selection

Use the `RunRecord` as the complete state of a run between processes. Its process-death fields
have complementary, current roles rather than replacements for one another: a resume stamps
`previous_process_died_at` when its predecessor's recorded PID is no longer running, while
`previous_process_pid` preserves that PID only for forensic inspection. Neither is a general
run-status field, and neither supersedes the other.

- rule: inspect `previous_process_died_at` with `terminal: null` to distinguish a dead-and-resumed attempt from an in-flight or wedged run; inspect `previous_process_pid` only when the prior process identity is needed for forensics
