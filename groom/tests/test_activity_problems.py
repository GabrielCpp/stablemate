from __future__ import annotations

from typing import Any

import pytest
from test_activity_groups import BASE, RETRIED, _attrs, _items, _polls, _seed
from test_run_clock import RUN, _DB, span

from groom import activity, overview, problems, store


def _flagged() -> list[dict[str, Any]]:
    return [
        entry
        for item in activity.timeline(RUN)["items"]
        for one in item["passes"]
        for entry in one["entries"]
        if entry.get("problem")
    ]


def _count() -> int:
    return activity.timeline(RUN)["problems"]


def _tile() -> int:
    return overview.run_overview(RUN)["standing"]["problems"]


def _churning(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_CHURN_REPEATS", "3")
    _seed()
    _polls()


def test_every_count_of_problems_reads_one_definition(monkeypatch: pytest.MonkeyPatch) -> None:
    with _DB():
        _churning(monkeypatch)
        spans = store.run_turn_spans(RUN)
        counts = (_count(), _tile(), len(_flagged()), len(problems.found(spans)), problems.standing(spans)["problems"])
    assert counts == (3, 3, 3, 3, 3)


def test_the_rows_the_problems_view_lists_are_as_many_as_the_count(monkeypatch: pytest.MonkeyPatch) -> None:
    with _DB():
        _churning(monkeypatch)
        rows = _flagged()
        count = _count()
    assert len(rows) == len({row["key"] for row in rows}) == count
    assert sorted(row["kind"] for row in rows) == ["churn", "failed", "retry"]


def test_an_answered_gate_is_no_problem_and_adds_nothing_to_the_count() -> None:
    with _DB():
        _seed()
        gates = [entry for item in _items().values() for one in item["passes"] for entry in one["entries"] if entry["kind"] == "gate"]
        counted = _count()
        store.insert_spans([span("g2", "t1", "sa", "resolve", "wait:operator", BASE + 400, 30, {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator", "workhorse.wait_outcome": "completed"} | _attrs("sign-in"), 1)])
        again = _count()
        flagged = [entry["kind"] for entry in _flagged()]
    assert gates and not any(entry.get("problem") for entry in gates)
    assert counted == again == 2
    assert "gate" not in flagged


def test_a_run_with_no_problems_counts_none() -> None:
    with _DB():
        store.insert_spans([span("r1", "t1", "", "coder", "run:coder", BASE, 100, {}, 1), span("n1", "t1", "r1", "lint", "lint", BASE + 1, 5, _attrs("sign-in"), 1)])
        counts = (_count(), _tile(), _flagged())
    assert counts == (0, 0, [])


def test_a_failed_agent_turn_and_a_failed_container_step_each_get_a_failed_row() -> None:
    with _DB():
        store.insert_spans([
            span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1),
            span("c1", "t1", "r1", "docs", "docs", BASE + 1, 100, _attrs("sign-in") | {"status_message": "docs step failed"}, 1) | {"status": "ERROR"},
            span("n1", "t1", "r1", "qa-story", "qa-story", BASE + 200, 100, _attrs("sign-in"), 1) | {"status": "ERROR"},
            span("a1", "t1", "n1", "qa-story", "agent_turn", BASE + 201, 90, _attrs("sign-in", model="m"), 1) | {"status": "ERROR"},
        ])
        keys = sorted(row["key"] for row in _flagged())
        failed = {row["key"]: row for row in _flagged()}
        counts = (_count(), _tile())
    assert keys == ["failed:a1", "failed:c1"]
    assert counts == (2, 2)
    assert "turn" in failed["failed:a1"] and "turn" not in failed["failed:c1"]


def test_the_failed_row_of_an_agent_turn_offers_the_turn_and_a_failed_step_does_not() -> None:
    with _DB():
        store.insert_spans([
            span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1),
            span("c1", "t1", "r1", "docs", "docs", BASE + 1, 100, _attrs("sign-in") | {"status_message": "docs step failed"}, 1) | {"status": "ERROR"},
            span("n1", "t1", "r1", "qa-story", "qa-story", BASE + 200, 100, _attrs("sign-in"), 1),
            span("a1", "t1", "n1", "qa-story", "agent_turn", BASE + 201, 90, _attrs("sign-in", **{"workhorse.visit.slug": RETRIED}), 1) | {"status": "ERROR"},
        ])
        turn = activity.entry(RUN, "failed:a1")
        step = activity.entry(RUN, "failed:c1")
    assert turn["next"]["key"] == RETRIED and turn["next"]["noun"] == "turn"
    assert turn["next"]["text"] == "qa-story is an agent turn."
    assert "is an agent turn" not in step["next"]["text"]


def test_a_gate_check_that_also_ended_in_error_counts_once() -> None:
    with _DB():
        store.insert_spans([
            span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1),
            span("g1", "t1", "r1", "run_gate", "run_gate", BASE + 1, 30, _attrs("sign-in") | {"workhorse.out.gate": "lint", "workhorse.out.status": "dirty"}, 1) | {"status": "ERROR"},
        ])
        counts = (_count(), _tile(), len(_flagged()))
        standing = overview.run_overview(RUN)["standing"]
    assert counts == (1, 1, 1)
    assert (standing["failed_steps"], standing["failed_gate_checks"]) == (0, 1)


def test_each_turn_after_the_first_of_a_visit_is_one_retry_row_that_names_its_turn() -> None:
    with _DB():
        _seed()
        retries = [entry for entry in _flagged() if entry["kind"] == "retry"]
    assert len(retries) == 1
    row = retries[0]
    assert (row["key"], row["name"], row["node"], row["turn"], row["ts"]) == ("retry:a-retry", "backend retry", "qa-story", RETRIED, BASE + 145)
    assert row["result"] == "qa-story turn started again after 30s, attempt 2"


def test_a_retry_reading_says_what_happened_and_links_to_its_turn() -> None:
    with _DB():
        _seed()
        reading = activity.entry(RUN, "retry:a-retry")
    assert reading["kind"] == "retry" and reading["key"] == "retry:a-retry"
    assert reading["head"]["name"] == "qa-story" and reading["head"]["flow"] == "qa" and reading["head"]["pass"] == 1
    assert reading["happened"] == "The backend started the qa-story turn again after the attempt before it ended. It waited 30s first."
    assert reading["next"] == {"key": RETRIED, "noun": "turn", "text": "This attempt finished and the turn went on."}


def test_a_retry_reading_claims_nothing_the_spans_do_not_record() -> None:
    with _DB():
        store.insert_spans([
            span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1),
            span("n1", "t1", "r1", "qa-story", "qa-story", BASE + 1, 400, _attrs("sign-in"), 1),
            span("a1", "t1", "n1", "qa-story", "agent_turn", BASE + 2, 100, _attrs("sign-in", **{"workhorse.visit.slug": RETRIED}), 1),
            span("a2", "t1", "n1", "qa-story", "agent_turn", BASE + 102, 100, _attrs("sign-in", **{"workhorse.visit.slug": RETRIED}), 1),
        ])
        row = next(entry for entry in _flagged() if entry["kind"] == "retry")
        reading = activity.entry(RUN, row["key"])
    assert row["result"] == "qa-story turn started again"
    assert reading["happened"] == "The backend started the qa-story turn again after the attempt before it ended."
    assert reading["next"]["text"] == "This attempt finished and the turn went on."
    assert "succeeded" not in reading["next"]["text"] and "did not finish" not in reading["happened"]


def test_a_retry_that_failed_as_well_says_so() -> None:
    with _DB():
        _seed()
        store.insert_spans([span("a-retry", "t1", "a-agent", "qa-story", "agent_turn", BASE + 145, 0, _attrs("sign-in", **{"workhorse.visit.slug": RETRIED}), 1) | {"status": "ERROR"}])
        reading = activity.entry(RUN, "retry:a-retry")
    assert reading["next"]["text"] == "The retry failed as well."


def test_a_churn_reading_says_what_repeated_and_what_came_next(monkeypatch: pytest.MonkeyPatch) -> None:
    with _DB():
        _churning(monkeypatch)
        key = next(row["key"] for row in _flagged() if row["kind"] == "churn")
        reading = activity.entry(RUN, key)
        store.insert_spans([span("after", "t1", "r1", "wrap", "wrap", BASE + 3000, 2, _attrs("reset"), 1)])
        later = activity.entry(RUN, key)
    assert reading["kind"] == "churn"
    assert reading["happened"] == "poll has run 3 times in a row on reset with the same labels. This alert means the run may be going round in circles."
    assert reading["next"]["key"] == "" and reading["next"]["text"] == "Nothing came after this."
    assert later["next"]["key"] == "step:after" and "wrap ran next and passed" in later["next"]["text"]


def test_a_retry_or_churn_key_the_run_does_not_hold_is_not_found() -> None:
    with _DB():
        _seed()
        for key in ("retry:nope", "churn:nope", "retry:a-turn:0"):
            with pytest.raises(activity.EntryNotFound):
                activity.entry(RUN, key)
