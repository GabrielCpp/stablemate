---
type: concept
slug: pyflow-activity
title: pyflow activity labels
---
# pyflow activity labels

Activity is a flagged log message projected onto the current telemetry labels. The
tracker preserves the last activity across state transitions, replaces workflow labels
wholesale on each transition, never drops the underlying log record, and swallows its
own instrumentation failures so observability cannot stop a run.

- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog` @fc149a498518
- tests: [activity tests](../../../../workhorse/tests/test_activity.py)
- detail: [Pyflow activity label documentation](pyflow-activity-label-selection.md)

## Fields

### field: FLAG
- type: `str`
- semantics: log-record extra key whose truthy value marks the record as the activity source
- verify: emitted(event="activity labels", count=1)
- code: `workhorse/workhorse/pyflow/activity.py::FLAG` @fc149a498518

### field: LABEL
- type: `str`
- semantics: telemetry label receiving the rendered flagged message
- verify: json_path(path="$.activity", matches=".+")
- code: `workhorse/workhorse/pyflow/activity.py::LABEL` @fc149a498518

## Methods

### ActivityLog.rebase
- sig: `rebase(labels: dict[str, str]) -> None`
- does: replaces base workflow labels and republishes the current activity if one exists
- verify: emitted(event="activity labels", count=1)
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog.rebase` @fc149a498518
- detail: [ActivityLog rebase documentation](activitylog-rebase-documentation.md)

### ActivityLog.filter
- sig: `filter(record: logging.LogRecord) -> bool`
- does: publishes a changed flagged log message as the current activity
- returns: `True` for every record, including records without the activity flag
- verify: emitted(event="activity labels", count=1)
- code: `workhorse/workhorse/pyflow/activity.py::ActivityLog.filter` @fc149a498518
- detail: [Pyflow activity label documentation](pyflow-activity-label-selection.md)

### install
- sig: `install(log: logging.Logger) -> ActivityLog`
- does: reuses an existing tracker on the logger or attaches one tracker
- returns: the tracker shared by parent and handed-off sub-workflows
- verify: count(subject="activity trackers attached to one logger", equals=1)
- code: `workhorse/workhorse/pyflow/activity.py::install` @fc149a498518
- detail: [Pyflow activity label documentation](pyflow-activity-label-selection.md)
