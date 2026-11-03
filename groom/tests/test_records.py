"""The raw record list of a run: its order, its pages, its counts, and the endpoint that serves it."""
from __future__ import annotations

import pytest
from litestar.testing import TestClient
from test_activity_groups import BASE, _seed
from test_app import _hermetic_client, _reset
from test_norms import _DB as _NormsDB
from test_norms import _feed, _wf
from test_run_clock import RUN, _DB

from groom import activity, projection, records, state, store
from groom.models import WorkflowContainer, WorkflowState


def _logs(count: int, *, at: float = BASE + 20, severity: str = "INFO") -> None:
    store.insert_logs([
        {"run_id": RUN, "node": "lint", "severity": severity, "body": f"line {number}", "ts": at + number} for number in range(count)
    ])


def _metrics(count: int) -> None:
    store.insert_metrics([
        {"run_id": RUN, "name": "workhorse.queue.depth", "ts": BASE + 30 + number, "value": float(number), "attrs": {"node": "lint"}}
        for number in range(count)
    ])


def _walk(metrics: bool = False, limit: int = 7) -> list[dict]:
    seen: list[dict] = []
    cursor = ""
    for _ in range(200):
        one = records.page(RUN, cursor, limit, metrics)
        seen += one["records"]
        cursor = one["next"]
        if not cursor:
            return seen
    raise AssertionError("the pages never ended")


def test_a_page_lists_spans_logs_events_and_alerts_newest_first_with_time_kind_node_and_text() -> None:
    with _DB():
        _seed()
        _logs(3)
        page = records.page(RUN)
    kinds = {one["kind"] for one in page["records"]}
    assert {"SPAN", "INFO", "EVENT"} <= kinds
    assert [one["ts"] for one in page["records"]] == sorted((one["ts"] for one in page["records"]), reverse=True)
    for one in page["records"]:
        assert one["time"] and one["kind"] and one["node"] and one["text"]


def test_a_span_record_is_written_when_the_span_ends_with_its_duration_and_cost() -> None:
    with _DB():
        _seed()
        spans = [one for one in records.page(RUN)["records"] if one["kind"] == "SPAN"]
    turn = next(one for one in spans if one["text"].startswith("agent_turn ended, 1m 40s"))
    assert turn["text"] == "agent_turn ended, 1m 40s, $2.00"
    failed = next(one for one in spans if one["node"] == "test")
    assert failed["text"] == "failed, 7.0s"
    assert failed["tone"] == "bad" and "$" not in failed["text"]


def test_a_retry_event_and_a_churn_alert_are_records_of_their_own(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_CHURN_REPEATS", "2")
    with _DB():
        _seed()
        found = records.page(RUN)["records"]
    assert any(one["kind"] == "EVENT" and one["text"].startswith("retry") for one in found)
    assert any(one["kind"] == "ALERT" and one["text"].startswith("CHURN:") for one in found)


def test_a_warning_log_reads_warn_and_an_error_log_is_marked_bad() -> None:
    with _DB():
        _seed()
        _logs(1, severity="WARNING")
        _logs(1, at=BASE + 50, severity="ERROR")
        found = records.page(RUN)["records"]
    assert next(one for one in found if one["kind"] == "WARN")["tone"] == "warn"
    assert next(one for one in found if one["kind"] == "ERROR")["tone"] == "bad"


def test_metric_samples_stay_out_until_asked_and_are_counted_either_way() -> None:
    with _DB():
        _seed()
        _metrics(5)
        hidden = records.page(RUN)
        shown = records.page(RUN, metrics=True)
    assert hidden["metric_samples"] == shown["metric_samples"] == 5
    assert not any(one["kind"] == "METRIC" for one in hidden["records"])
    assert sum(one["kind"] == "METRIC" for one in shown["records"]) == 5
    assert shown["total"] == hidden["total"] + 5


def test_the_total_counts_every_record_of_the_run_not_the_page() -> None:
    with _DB():
        _seed()
        _logs(30)
        every = _walk()
        page = records.page(RUN, limit=5)
    assert page["total"] == len(every)
    assert len(page["records"]) == 5 and page["next"]


def test_paging_by_the_cursor_loses_and_repeats_no_record() -> None:
    with _DB():
        _seed()
        _logs(40, at=BASE + 20)
        _metrics(9)
        for metrics in (False, True):
            keys = [one["key"] for one in _walk(metrics)]
            assert len(keys) == len(set(keys))
            assert len(keys) == records.page(RUN, metrics=metrics, limit=records.PAGE)["total"]


def test_the_last_page_has_no_cursor_and_a_full_page_with_nothing_older_has_none_either() -> None:
    with _DB():
        _seed()
        total = records.page(RUN)["total"]
        exact = records.page(RUN, limit=total)
        short = records.page(RUN, limit=total - 1)
    assert exact["next"] == "" and short["next"] != ""


def test_records_with_the_same_time_keep_one_total_order_across_pages() -> None:
    with _DB():
        _seed()
        store.insert_logs([{"run_id": RUN, "node": "lint", "severity": "INFO", "body": f"same {number}", "ts": BASE + 99} for number in range(9)])
        walked = _walk(limit=2)
    keys = [one["key"] for one in walked]
    assert len(keys) == len(set(keys))
    same = [one for one in walked if one["ts"] == BASE + 99]
    assert [one["text"] for one in same] == [f"same {number}" for number in reversed(range(9))]


def test_a_page_is_capped_and_a_cursor_that_does_not_parse_is_refused() -> None:
    with _DB():
        _seed()
        assert len(records.page(RUN, limit=10_000)["records"]) <= records.PAGE
        with pytest.raises(records.BadCursor):
            records.page(RUN, "not-a-cursor")


def test_the_store_pages_metric_samples_by_a_cursor_and_counts_them() -> None:
    with _DB():
        _metrics(6)
        first = store.detail_metrics(RUN, 4)
        rest = store.detail_metrics(RUN, 4, (first[-1]["ts"], 1, first[-1]["id"]))
        assert store.count_metrics(RUN) == 6
    assert [one["value"] for one in first] == [5.0, 4.0, 3.0, 2.0]
    assert [one["value"] for one in rest] == [1.0, 0.0]


def test_the_records_endpoint_serves_a_page_and_refuses_a_bad_cursor() -> None:
    with _DB():
        _seed()
        _logs(10)
        client = _hermetic_client()
        try:
            good = client.get(f"/api/run/{RUN}/records?limit=5")
            more = client.get(f"/api/run/{RUN}/records", params={"limit": 5, "before": good.json()["next"], "metrics": 1})
            bad = client.get(f"/api/run/{RUN}/records?before=zzz")
        finally:
            client.__exit__(None, None, None)
    assert good.status_code == 200 and len(good.json()["records"]) == 5
    assert more.json()["metrics"] is True
    assert bad.status_code == 400


def test_the_activity_timeline_adds_info_logs_inside_the_pass_they_belong_to_without_splitting_a_fold() -> None:
    with _DB():
        _seed()
        _logs(2, at=BASE + 14)
        plain = activity.timeline(RUN)
        with_logs = activity.timeline(RUN, logs=True)
    assert plain["log_count"] == with_logs["log_count"] == 2

    def kinds(timeline: dict) -> list[str]:
        return [entry["kind"] for item in timeline["items"] for one in item["passes"] for entry in one["entries"]]

    assert "log" not in kinds(plain)
    assert kinds(with_logs).count("log") == 2
    assert [kind for kind in kinds(with_logs) if kind != "log"] == kinds(plain)
    folds = [entry for item in with_logs["items"] for one in item["passes"] for entry in one["entries"] if entry["kind"] == "steps"]
    assert all(len(fold["steps"]) == fold["count"] for fold in folds)


def test_a_debug_log_is_not_a_timeline_row_but_raw_lists_it() -> None:
    with _DB():
        _seed()
        _logs(1, severity="DEBUG")
        timeline = activity.timeline(RUN, logs=True)
        found = records.page(RUN)["records"]
    assert timeline["log_count"] == 0
    assert any(one["kind"] == "DEBUG" for one in found)


def test_the_running_strip_carries_the_time_the_node_began() -> None:
    with _NormsDB():
        tel = _feed([
            ("workhorse.node.active", 1.0, {}),
            ("workhorse.node.elapsed_s", 900.0, {}),
        ], now=5000.0)
        strip = projection.running_strip(_wf(), tel, None, now=5000.0)
        state.RUNS.pop("r1", None)
    assert strip is not None
    assert strip["node_since_ts"] == 5000.0 - 900.0


def test_the_worker_endpoint_still_answers_with_history_and_metrics_for_the_terminal_client() -> None:
    _reset()
    state.WORKFLOWS["abc123"] = WorkflowContainer(container_id="abc123", name="w", state=WorkflowState.RUNNING, current_node="write_epic", run_id="run-1")
    client: TestClient = _hermetic_client()
    try:
        detail = client.get("/worker/abc123").json()
    finally:
        client.__exit__(None, None, None)
    assert "history" in detail and "metrics" in detail
    assert detail["metrics"]["cells"] is not None
