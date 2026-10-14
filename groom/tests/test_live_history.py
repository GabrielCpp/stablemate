"""Ingested history preserves ordering, bounds, and span upsert semantics."""
from __future__ import annotations

import json

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


def test_metric_samples_cannot_evict_older_completed_span_history():
    history = LiveHistory(log_limit=3)
    history.update_spans([{
        "span_id": "old", "start_ts": 1, "end_ts": 2, "status": "OK", "name": "plan"
    }])
    history.update_metrics([
        {"name": "workhorse.node.elapsed_s", "ts": ts, "value": ts, "attrs": {}}
        for ts in range(100, 110)
    ])
    rows = history.recent()
    assert len([row for row in rows if row["kind"] == "metric"]) == 3
    assert [row["name"] for row in rows if row["kind"] == "span"] == ["plan"]


def _line(update: dict, ts: float = 1.0, node: str = "implement") -> bytes:
    record = {"sessionId": "s", "update": update, "_meta": {"ts": ts, "node": node}}
    return (json.dumps(record) + "\n").encode()


def _call(call_id: str, ts: float = 1.0) -> bytes:
    return _line(
        {"sessionUpdate": "tool_call", "toolCallId": call_id, "title": "Read a.py",
         "kind": "read", "status": "in_progress"},
        ts,
    )


def _done(call_id: str, ts: float = 2.0, status: str = "completed") -> bytes:
    return _line(
        {"sessionUpdate": "tool_call_update", "toolCallId": call_id, "status": status,
         "content": [{"type": "content", "content": {"type": "text", "text": "ok"}}],
         "rawOutput": "ok"},
        ts,
    )


def test_a_tool_call_update_merges_into_its_call_by_tool_call_id():
    history = LiveHistory(log_limit=3)
    history.feed_transcript("001-00001-implement", _call("t1") + _done("t1"))
    rows = [row for row in history.recent() if row["kind"] == "transcript"]
    assert len(rows) == 1
    update = rows[0]["update"]
    assert update["sessionUpdate"] == "tool_call"
    assert update["title"] == "Read a.py"
    assert update["status"] == "completed"
    assert update["rawOutput"] == "ok"
    assert update["content"][0]["content"]["text"] == "ok"


def test_an_update_whose_call_was_never_seen_is_kept_as_its_own_entry():
    history = LiveHistory(log_limit=3)
    history.feed_transcript("001-00001-implement", _done("lost", status="failed"))
    rows = [row for row in history.recent() if row["kind"] == "transcript"]
    assert [row["update"]["status"] for row in rows] == ["failed"]


def test_a_call_and_its_update_merge_across_two_feeds():
    history = LiveHistory(log_limit=3)
    history.feed_transcript("001-00001-implement", _call("t1"))
    history.feed_transcript("001-00001-implement", _done("t1"))
    rows = [row for row in history.recent() if row["kind"] == "transcript"]
    assert [row["update"]["status"] for row in rows] == ["completed"]


def test_an_entry_keeps_its_key_when_later_lines_and_split_reads_arrive():
    slug = "001-00001-implement"
    first, second = _call("t1", ts=1.0), _call("t2", ts=2.0)
    history = LiveHistory(log_limit=3)
    history.feed_transcript(slug, first + second[:10])
    history.feed_transcript(slug, second[10:])
    keys = [row["key"] for row in reversed(history.recent()) if row["kind"] == "transcript"]
    assert keys == [f"{slug}:0", f"{slug}:{len(first)}"]


def test_transcript_entries_have_their_own_limit_and_cannot_push_spans_out():
    history = LiveHistory(log_limit=3, transcript_limit=2)
    history.update_spans([{
        "span_id": "s", "start_ts": 1, "end_ts": 2, "status": "OK", "name": "plan"
    }])
    chunk = b"".join(
        _line({"sessionUpdate": "agent_message_chunk",
               "content": {"type": "text", "text": f"m{n}"}}, 100 + n)
        for n in range(5)
    )
    history.feed_transcript("001-00001-implement", chunk)
    rows = history.recent()
    texts = [row["update"]["content"]["text"] for row in rows if row["kind"] == "transcript"]
    assert texts == ["m4", "m3"]
    assert [row["name"] for row in rows if row["kind"] == "span"] == ["plan"]


def test_recent_orders_transcript_entries_with_the_other_families_by_timestamp():
    history = LiveHistory(log_limit=5)
    history.update_logs([{"body": "log", "ts": 15.0}])
    history.update_spans([{
        "span_id": "s", "start_ts": 1, "end_ts": 25.0, "status": "OK", "name": "turn"
    }])
    history.feed_transcript(
        "001-00001-implement",
        _line({"sessionUpdate": "agent_message_chunk",
               "content": {"type": "text", "text": "hi"}}, 20.0),
    )
    assert [row["kind"] for row in history.recent()] == ["span", "transcript", "log"]
    assert history.recent()[1]["ts"] == 20.0


def test_a_partial_trailing_line_is_held_until_its_newline_arrives():
    history = LiveHistory(log_limit=3)
    whole = _call("t1")
    history.feed_transcript("001-00001-implement", whole[:20])
    assert [row for row in history.recent() if row["kind"] == "transcript"] == []
    history.feed_transcript("001-00001-implement", whole[20:])
    assert len([row for row in history.recent() if row["kind"] == "transcript"]) == 1
    assert history.offsets["001-00001-implement"] == len(whole)


def test_a_truncation_marker_becomes_a_visible_entry():
    history = LiveHistory(log_limit=3)
    history.feed_transcript(
        "001-00001-implement", _call("t1", 5.0) + b'{"truncated": true, "bytes": 99}\n'
    )
    kinds = [row["update"]["sessionUpdate"] for row in history.recent()]
    assert "truncated" in kinds


def test_a_line_that_is_not_json_is_skipped():
    history = LiveHistory(log_limit=3)
    history.feed_transcript("001-00001-implement", b"not json\n" + _call("t1"))
    assert len([row for row in history.recent() if row["kind"] == "transcript"]) == 1
