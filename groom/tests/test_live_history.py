"""Ingested history preserves ordering, bounds, and span upsert semantics."""
from __future__ import annotations

from groom.live_history import LiveHistory


def test_late_logs_do_not_displace_newer_lines_and_the_trail_is_bounded():
    history = LiveHistory(log_limit=3)
    history.update_logs([{"body": "first", "ts": 2}, {"body": "newest", "ts": 3}])
    history.update_logs([
        {"body": "late", "ts": 1}, {"body": "tie", "ts": 3}, {"body": "old", "ts": 0}
    ])
    assert [row["body"] for row in history.logs] == ["tie", "newest", "first"]


def test_replaced_span_updates_errors_without_counting_another_span():
    history = LiveHistory(log_limit=3)
    span = {"span_id": "a", "start_ts": 1, "end_ts": 2, "status": "ERROR"}
    history.update_spans([span, span])
    assert history.facts()["span_count"] == 1
    assert history.facts()["error_count"] == 1
    history.update_spans([{**span, "status": "OK"}])
    assert history.facts()["span_count"] == 1
    assert history.facts()["error_count"] == 0
