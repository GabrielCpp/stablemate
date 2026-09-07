---
type: concept
slug: runner-result-field-selection
title: Runner result field selection
---
# Runner result field selection

`RunnerResult` is the authoritative final record of a detached command's termination and cost.
`collect` reads the supervisor's `runner.json` record into this complete value, and `kill` returns
the same value after either the supervisor or its fallback writes the record. Use the complete
record when handing a job's final outcome to another operation or preserving its measurements.

Use a named field only when the consumer needs that one measurement: `exit_code` for command
outcome, `peak_rss_mb` and `wall_s` for cost, `kill_reason` for termination classification,
`tier` for measurement context, and `started_at` and `finished_at` for timing. The fields are
not alternative result representations; together they are the record returned by the job API.

- code: `workhorse/workhorse/job.py::RunnerResult`
- rule: use `RunnerResult` for a job's complete final outcome; read an individual field only for the measurement that consumer needs
- prefers: [RunnerResult](job-supervisor.md#field-runnerresult)
