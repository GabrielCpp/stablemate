"""What the run is working on *right now*, taken from the log line that said so."""
from __future__ import annotations

import logging

from workhorse import otel

FLAG = "activity"

LABEL = "activity"


class ActivityLog(logging.Filter):
    """Publishes the last flagged log message as the `activity` label."""

    def __init__(self) -> None:
        super().__init__()
        self._base: dict[str, str] = {}
        self._text = ""

    def rebase(self, labels: dict[str, str]) -> None:
        """Replace the workflow's declared labels, keeping the current activity."""
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
    """Attach a tracker to `log`, or return the one already attached."""
    for existing in log.filters:
        if isinstance(existing, ActivityLog):
            return existing
    tracker = ActivityLog()
    log.addFilter(tracker)
    return tracker


__all__ = ["FLAG", "LABEL", "ActivityLog", "install"]
