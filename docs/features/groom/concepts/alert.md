---
type: concept
slug: alert
title: Alert
---
# Alert

An alert is one newly-fired notification produced by the telemetry hot-cache rules. Its [`rule`](#rule)
identifies the condition, its [`run_id`](#run_id) identifies the affected run, and its [`message`](#message)
gives the operator the evidence and current location needed to act. The alert engine deduplicates each rule
per run until recovery, forward progress, wait closure, or a resumed session retires that rule.

- code: `groom/groom/alerts.py::Alert`
- rule: [`run_id`](#run_id), [`rule`](#rule), and [`message`](#message) are the three required fields of one `Alert` record, not
  alternate implementations of each other — no ranking applies. All three are set together on
  every construction and each covers a distinct piece of the notification: which run, what
  condition fired, and the human-readable evidence for it.
- tests: `groom/tests/test_telemetry.py::test_watchdog_and_giveup_fire_once_per_run`

## Fields

### run_id

- type: `str`
- default: none
- required: true
- semantics: identifies the originating run, copied from the RunTelemetry's `run_id` at the moment the rule fires via `_fire` (`alerts.py:170-174`)
- verify: json_path(path="$.run_id", matches="^.+$")
- code: `groom/groom/alerts.py::Alert.run_id`
- tests: `groom/tests/test_telemetry.py::test_watchdog_and_giveup_fire_once_per_run`
- detail: [run telemetry](run-telemetry.md#field-run-id)

### rule

- type: `str`
- default: none
- required: true
- semantics: names the alert condition, one of `STALL`, `STUCK`, `CHURN`, `WATCHDOG`, `GAVE-UP`, `ENDED`, `DIED`, `BLOCKED`, or `WAITING`.
- code: `groom/groom/alerts.py::Alert`
- detail: [Alert](alert.md)

### message

- type: `str`
- default: none
- required: true
- semantics: human-readable operator-facing evidence — the run label, the rule-specific phrasing, and (when known) the run's current node.
- verify: json_path(path="$.message", matches="^.+$")
- code: `groom/groom/alerts.py::Alert.message`
- tests: `groom/tests/test_telemetry.py::test_a_run_that_dies_pages_instead_of_quietly_leaving_the_queue_idle`
- detail: [dashboard notify message](../dashboard-notify-message.md#field-message)
