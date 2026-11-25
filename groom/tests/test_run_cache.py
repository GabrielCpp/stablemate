"""A run's kept span list answers as a fresh read of the store does after every batch that lands on the run."""
from __future__ import annotations

from typing import Any

from test_run_clock import RUN, _DB, span

from groom import store
from groom.span_views import view
from groom.store import run_cache

SESSION = "sess-1"


def _turn(span_id: str, at: float, reported: float, session: str = SESSION) -> dict:
    attrs = {"backend": "claude", "model": "opus", "session.id": session, "total_cost_usd": reported, "usage.output_tokens": 10, "work_id": "w1"}
    return span(span_id, "t1", "n1", "dev", "agent_turn", at, 5, attrs, 1)


def _fresh() -> list[dict[str, Any]]:
    run_cache.forget()
    return list(run_cache.run_spans(RUN))


def _charges(spans: list[dict[str, Any]]) -> dict[str, float]:
    return {one["span_id"]: one["profile_cost_usd"] for one in spans if one["name"] == "agent_turn"}


def test_a_batch_that_adds_spans_shows_in_the_next_read() -> None:
    with _DB():
        store.insert_spans([span("r1", "t1", "", "coder", "run:coder", 0, 100, {}, 1), _turn("a", 10, 1.0)])
        first = run_cache.run_spans(RUN)
        store.insert_spans([_turn("b", 30, 3.0)])
        kept = list(run_cache.run_spans(RUN))
        fresh = _fresh()
    assert [one["span_id"] for one in first] == ["r1", "a"]
    assert kept == fresh
    assert _charges(kept) == {"a": 1.0, "b": 2.0}


def test_a_turn_that_lands_late_reprices_the_later_turns_of_its_session() -> None:
    with _DB():
        store.insert_spans([_turn("a", 10, 1.0), _turn("c", 30, 3.0)])
        before = _charges(run_cache.run_spans(RUN))
        store.insert_spans([_turn("b", 20, 2.5)])
        kept = list(run_cache.run_spans(RUN))
        fresh = _fresh()
    assert before == {"a": 1.0, "c": 2.0}
    assert _charges(kept) == {"a": 1.0, "b": 1.5, "c": 0.5}
    assert kept == fresh


def test_a_span_written_again_replaces_its_kept_copy() -> None:
    with _DB():
        store.insert_spans([_turn("a", 10, 1.0)])
        run_cache.run_spans(RUN)
        again = _turn("a", 10, 1.0)
        again["status"] = "ERROR"
        store.insert_spans([again])
        kept = list(run_cache.run_spans(RUN))
        fresh = _fresh()
    assert [one["status"] for one in kept] == ["ERROR"]
    assert kept == fresh


def test_a_view_built_on_a_kept_list_is_built_again_after_a_batch() -> None:
    calls: list[int] = []

    def counted() -> int:
        calls.append(1)
        return len(calls)

    with _DB():
        store.insert_spans([_turn("a", 10, 1.0)])
        first = view(run_cache.run_spans(RUN), "probe", counted)
        same = view(run_cache.run_spans(RUN), "probe", counted)
        store.insert_spans([_turn("b", 30, 3.0)])
        after = view(run_cache.run_spans(RUN), "probe", counted)
    assert (first, same, after) == (1, 1, 2)


def test_a_new_store_never_serves_the_spans_kept_from_the_last_one() -> None:
    with _DB():
        store.insert_spans([_turn("a", 10, 1.0)])
        assert [one["span_id"] for one in run_cache.run_spans(RUN)] == ["a"]
    with _DB():
        store.insert_spans([_turn("z", 10, 1.0)])
        assert [one["span_id"] for one in run_cache.run_spans(RUN)] == ["z"]


def test_a_span_changed_in_place_is_read_again() -> None:
    with _DB():
        store.insert_spans([_turn("a", 10, 1.0)])
        run_cache.run_spans(RUN)
        with store.STORE.writing() as conn:
            conn.execute("UPDATE spans SET run_dir = '/moved' WHERE span_id = 'a'")
        kept = list(run_cache.run_spans(RUN))
    assert [one["run_dir"] for one in kept] == ["/moved"]


def test_a_run_deleted_and_written_again_with_the_same_row_ids_is_read_again() -> None:
    with _DB():
        store.insert_spans([_turn("a", 10, 1.0), _turn("b", 20, 2.0)])
        run_cache.run_spans(RUN)
        store.delete_run_telemetry(RUN)
        store.insert_spans([_turn("x", 10, 1.0), _turn("y", 20, 2.0)])
        kept = [one["span_id"] for one in run_cache.run_spans(RUN)]
    assert kept == ["x", "y"]
