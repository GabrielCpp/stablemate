---
type: concept
slug: activity-labels
title: Activity labels from flagged logs
---
# Activity labels from flagged logs

Python workflow activity is declared by an ordinary log record carrying
`extra={"activity": True}`. The rendered message becomes the unprefixed `activity` telemetry
label. The last non-empty flagged message is sticky across state transitions, while ordinary log
records do not replace it. Workflow labels are rebased wholesale on each transition; the sticky
activity is retained and re-published with the new base labels.

The tracker is installed as a logger filter, never drops records, and swallows malformed
format-string failures. Installing it repeatedly on the same logger returns the existing tracker,
which preserves activity across recursive sub-workflow handoffs. Live metrics promote both raw
`activity`/`work_id` and legacy `wf.activity`/`wf.work_id` spellings, but no other labels, to keep
metric cardinality bounded.

- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog`
- code: `workhorse/workhorse/pyflow/activity.py::install`
- code: `workhorse/workhorse/pyflow/activity.py::FLAG`
- code: `workhorse/workhorse/pyflow/activity.py::LABEL`
- tests: `workhorse/tests/test_activity.py`
- detail: [OpenTelemetry instrumentation](telemetry-instrumentation.md)

## Methods

### rebase
- sig: `ActivityLog.rebase(labels: dict[str, str]) -> None`
- does: replaces the workflow-declared base labels and publishes them together with the current activity when present
- verify: unchanged(subject="current activity label across workflow label rebase")
- verify: emitted(event="activity labels after workflow label rebase", count=1)
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog.rebase`

### filter
- sig: `ActivityLog.filter(record: logging.LogRecord) -> bool`
- does: replaces the activity label with the rendered message when the record carries the activity flag and the message is non-empty and changed
- verify: emitted(event="activity labels", count=1)
- does: keeps the previous activity when message rendering fails or produces an empty message
- verify: unchanged(subject="activity label after malformed or empty flagged record")
- returns: `True` for every record so the filter never suppresses logging
- verify: emitted(event="every filtered log record", count=1)
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog.filter`

### install
- sig: `install(log: logging.Logger) -> ActivityLog`
- does: returns the existing `ActivityLog` filter on the logger when one is already attached
- verify: count(subject="activity trackers attached to the logger", equals=1)
- does: attaches and returns one new tracker when the logger has none
- verify: created(subject="activity tracker attached to the logger")
- returns: the logger's single activity tracker
- verify: count(subject="activity trackers attached to the logger", equals=1)
- code: `workhorse/workhorse/pyflow/activity.py::install`
