---
type: concept
slug: alert
title: Alert
---
# Alert

An alert is one newly-fired notification produced by the telemetry hot-cache rules. Its `rule`
identifies the condition, its `run_id` identifies the affected run, and its message gives the
operator the evidence and current location needed to act. The alert engine deduplicates each rule
per run until recovery, forward progress, wait closure, or a resumed session retires that rule.

- code: `groom/groom/alerts.py::Alert`
- rule: `run_id`, `rule`, and `message` are the three required fields of one `Alert` record, not
  alternate implementations of each other — no ranking applies. All three are set together on
  every construction and each covers a distinct piece of the notification: which run, what
  condition fired, and the human-readable evidence for it.
- tests: `groom/tests/test_telemetry.py::test_watchdog_and_giveup_fire_once_per_run`

## Fields

### run_id

- type: `str`
- default: none
- required: true
- semantics: identifies the run whose telemetry caused the notification.
- code: `groom/groom/alerts.py::Alert`
- detail: [Alert](alert.md)

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
- semantics: human-readable notification text containing the run label and rule-specific evidence.
- code: `groom/groom/alerts.py::Alert`
- detail: [Alert](alert.md)
