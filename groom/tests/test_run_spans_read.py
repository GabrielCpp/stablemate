"""A run's span read keeps the columns and attributes its readers use and answers as the full read did."""
from __future__ import annotations

import json
from typing import Any

import pytest

from groom import activity, history, records, store
from groom.store import profile as store_profile
from tests.test_row_figures import _DB
from tests.test_row_figures import _span as _base


def _span(span_id: str, parent: str, node: str, name: str, attrs: dict, at: float, seconds: float = 60, status: str = "OK", generation: int = 0) -> dict:
    heavy = {
        "workhorse.repositories.start": "https://example.com/acme/api-service " * 50,
        "workhorse.repositories.end": "https://example.com/acme/api-service " * 50,
        "workspace.path.start": "/srv/api-service",
        "git.head.start": "abc123",
        "git.branch.start": "main",
    }
    return {
        **_base(span_id, parent, node, name, {**heavy, **attrs}, at, seconds),
        "run_dir": "/srv/api-service",
        "status": status,
        "resume_generation": generation,
    }


def _seed() -> None:
    turn = {
        "work_id": "w1", "backend": "claude", "model": "opus", "session.id": "sess-1",
        "total_cost_usd": 1.5, "usage.output_tokens": 100, "duration_ms": 60000,
        "review_verdict": "pass", "fix.attempt": "2",
        "events": [{"name": "e", "ts": 130.0, "attrs": {"k": "v"}}],
    }
    spans = [
        _span("root", "", "", "run:coder", {"workhorse.terminal": "terminal"}, 100, 2000),
        _span("s0", "root", "work", "work", {"workhorse.span_kind": "state", "workhorse.depth": 0}, 100, 1000),
        _span("w1", "s0", "wait", "wait", {
            "workhorse.span_kind": "wait", "workhorse.wait_kind": "operator",
            "workhorse.gate_path": "/gates/one", "workhorse.gate_question": "Proceed?",
            "workhorse.wait_outcome": "completed",
        }, 300, 30, generation=1),
        _span("e1", "s0", "build", "build", {"workhorse.depth": 1, "status_message": "boom"}, 400, 20, status="ERROR", generation=1),
    ]
    for index in range(4):
        at = 500 + index * 100
        spans.append(_span(f"n{index}", "s0", "qa", "qa", {"workhorse.depth": 1, "stage": "review"}, at, 40, generation=index % 2))
        spans.append(_span(f"t{index}", f"n{index}", "qa", "agent_turn", dict(turn), at + 5, 30, generation=index % 2))
    store.insert_spans(spans)


def _full_spans(run: str) -> list[dict[str, Any]]:
    rows = (
        store.read_connection()
        .execute(
            f"{store._charges('run_id = ?')}SELECT {store._SPAN_COLUMNS}, {store._duration} AS profile_duration_ms,"
            f" {store._charge} AS profile_cost_usd, {store._output} AS profile_output_tokens,"
            f" {store._input} AS profile_input_tokens, {store._cache_read} AS profile_cache_read_tokens,"
            f" {store._cache_write} AS profile_cache_write_tokens,"
            " est_cost_usd, spans.rowid AS row_id, resume_generation"
            " FROM spans LEFT JOIN charges USING (span_id)"
            " WHERE run_id = ? ORDER BY start_ts",
            (run, run),
        )
        .fetchall()
    )
    return [{**dict(row), "attrs": json.loads(row["attrs_json"] or "{}")} for row in rows]


def test_a_run_span_read_drops_the_unread_columns_and_attributes() -> None:
    with _DB():
        _seed()
        spans = store.run_turn_spans("run-1")
    assert spans
    span = spans[0]
    assert "attrs_json" not in span
    assert "repositories_start" not in span
    assert all("workhorse.repositories.start" not in one["attrs"] for one in spans)
    assert all("workhorse.repositories.end" not in one["attrs"] for one in spans)
    turn = next(one for one in spans if one["name"] == "agent_turn")
    assert turn["attrs"]["review_verdict"] == "pass"
    assert turn["attrs"]["events"][0]["name"] == "e"
    assert turn["attrs"]["git.head.start"] == "abc123"
    root = next(one for one in spans if one["name"] == "run:coder")
    assert root["attrs"]["workhorse.terminal"] == "terminal"


def test_every_reader_answers_as_it_did_on_the_full_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_CHURN_REPEATS", "2")

    def readers() -> list[Any]:
        return [
            store.run_profile("run-1"),
            store.run_flows("run-1"),
            {**activity.timeline("run-1"), "as_of": 0},
            activity.search("run-1", "e"),
            records.page("run-1"),
            history.summarize("run-1", now=10_000.0),
        ]

    with _DB():
        _seed()
        lean = readers()
        with monkeypatch.context() as patch:
            patch.setattr(store_profile, "_run_spans", _full_spans)
            full = readers()
    assert lean[0] is not None
    assert lean == full
