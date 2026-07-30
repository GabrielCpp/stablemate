"""What the run is working on *right now*, taken from the log line that said so.

The YAML engine has a per-node `activity:` field: a Jinja string re-rendered before
each node and stamped as a label so a dashboard can show "authoring epic E-4" rather
than a node id. A state machine has no per-node field to hang that on — a state is
one method that may do several things, and the interesting one is whichever it is
doing now. So the signal is a **flagged log record** instead:

    logger.info("assessing %s", unit_id, extra={"activity": True})

The rendered message *is* the activity. `activity` is a flag, not a value, so the
text is never written twice and never drifts from what the log says. It works
identically from a state (`self.logger`) and from a node (its injected `logger`) —
the same logger object — and for a node it is the only route, since a node is a plain
function with no `self`.

It is **sticky**: the last flagged line stands until another replaces it, so a state
that flags once and then works for an hour stays correctly labelled. A consumer that
has never seen one falls back to the node id, which the gauges stamp anyway.

Unlike the YAML engine's labels these keys are **not** `wf.`-prefixed. The prefix
existed so a workflow could not shadow an OTel convention; here the collector reads
the unprefixed spelling instead, and no translation happens on the way out.
"""
from __future__ import annotations

import logging

from workhorse import otel

#: The `extra=` key a log record sets to nominate itself as the run's activity.
FLAG = "activity"

#: The label the flagged message is published under.
LABEL = "activity"


class ActivityLog(logging.Filter):
    """Publishes the last flagged log message as the `activity` label.

    A filter rather than a handler because it must see records regardless of where
    they are eventually written — a run with no collector, no file handler and only a
    console still knows what it is doing. It never drops a record: the return value is
    always True, and its own failure modes are swallowed, because instrumentation that
    can suppress a log line or fail a run is worse than no instrumentation.
    """

    def __init__(self) -> None:
        super().__init__()
        self._base: dict[str, str] = {}
        self._text = ""

    def rebase(self, labels: dict[str, str]) -> None:
        """Replace the workflow's declared labels, keeping the current activity.

        Called once per transition, in place of the direct `otel.set_labels` the
        driver used to make — the labels are still replaced wholesale, and the
        activity rides along rather than being cleared by every state change.
        """
        self._base = dict(labels)
        self._publish()

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, FLAG, False):
            try:
                text = record.getMessage()
            except Exception:  # noqa: BLE001 — a %-args mismatch must not fail the run
                text = ""
            if text and text != self._text:
                self._text = text
                self._publish()
        return True

    def _publish(self) -> None:
        labels = dict(self._base)
        if self._text:
            labels[LABEL] = self._text
        otel.set_labels(labels)


def install(log: logging.Logger) -> ActivityLog:
    """Attach a tracker to `log`, or return the one already attached.

    Idempotent because `handoff` drives a sub-workflow through a recursive `drive()`
    on the same logger: a second tracker would publish over the first, and the
    activity a sub-flow sets would be lost the moment the parent transitioned. One
    tracker per logger, shared across the whole run.
    """
    for existing in log.filters:
        if isinstance(existing, ActivityLog):
            return existing
    tracker = ActivityLog()
    log.addFilter(tracker)
    return tracker


__all__ = ["FLAG", "LABEL", "ActivityLog", "install"]
