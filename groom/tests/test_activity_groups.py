"""The Activity timeline grouped by work item and flow pass: headings, folded steps, and the rows around the turns."""
from __future__ import annotations

from typing import Any

import pytest
from test_activity import _claude, _write
from test_run_clock import RUN, STATE, _DB, span

from groom import activity, store, turns

BASE = 1_700_000_000.0


def _attrs(work_id: str, **extra: Any) -> dict:
    return ({"work_id": work_id} if work_id else {}) | extra


def _pass(tag: str, flow: str, at: float, work_id: str, steps: list[tuple[str, float, str]], *, turn: tuple[float, float] | None = None, events: list[dict] | None = None, slug: str = "", session: str = "") -> list[dict]:
    spans = [
        span(f"f{tag}", "t1", "r1", flow, flow, at, 500, {"workhorse.depth": 0} | _attrs(work_id), 1),
        span(f"s{tag}", "t1", f"f{tag}", "work", "work", at + 1, 480, STATE | _attrs(work_id), 1),
    ]
    cursor = at + 2
    for name, seconds, status in steps:
        one = span(f"{tag}-{name}", "t1", f"s{tag}", name, name, cursor, seconds, {"workhorse.depth": 2} | _attrs(work_id), 1)
        one["status"] = status
        if status == "ERROR":
            one["attrs"]["status_message"] = "2 tests failed"
        spans.append(one)
        cursor += seconds + 1
    if turn is not None:
        seconds, cost = turn
        node = span(f"{tag}-agent", "t1", f"s{tag}", "qa-story", "qa-story", cursor, seconds + 5, {"workhorse.depth": 2} | _attrs(work_id), 1)
        agent = span(f"{tag}-turn", "t1", f"{tag}-agent", "qa-story", "agent_turn", cursor + 1, seconds, _attrs(work_id, model="m", total_cost_usd=cost, duration_ms=seconds * 1000, **({"events": events} if events else {}), **({"workhorse.visit.slug": slug} if slug else {}), **({"session.id": session} if session else {})), 1)
        agent["profile_cost_usd"] = cost
        spans += [node, agent]
    return spans


def _seed(run: str = RUN) -> None:
    spans = [span("r1", "t1", "", "coder", "run:coder", BASE, 5000, {}, 1)]
    spans += _pass("a", "qa", BASE + 10, "sign-in", [("lint", 5, "UNSET"), ("build", 6, "UNSET"), ("test", 7, "ERROR"), ("pack", 8, "UNSET")], turn=(100, 2.0), events=[{"name": "retry", "ts": BASE + 40, "attrs": {"node": "qa-story", "attempt": "2", "delay_s": "30"}}])
    spans += _pass("b", "qa", BASE + 700, "sign-in", [("lint", 5, "UNSET")], turn=(50, 1.0))
    spans += _pass("c", "qa", BASE + 1400, "reset", [("lint", 5, "UNSET")], turn=(70, 3.0))
    gate = span("g1", "t1", "sa", "resolve", "wait:operator", BASE + 50, 30, {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator", "workhorse.wait_outcome": "completed", "activity": "escalation #1: docs block"} | _attrs("sign-in"), 1)
    spans.append(gate)
    for one in spans:
        one["run_id"] = run
    store.insert_spans(spans)


def _polls(count: int = 3, run: str = RUN) -> None:
    store.insert_spans([span(f"p{number}", "t1", "sc", "poll", "poll", BASE + 1500 + number * 3, 2, {"workhorse.depth": 2} | _attrs("reset"), 1, run) for number in range(count)])


def _items() -> dict[str, dict]:
    return {item["work_id"]: item for item in activity.timeline(RUN)["items"]}


def test_rows_group_under_a_work_item_with_its_state_time_and_cost() -> None:
    with _DB():
        _seed()
        items = _items()
    assert list(items) == ["sign-in", "reset"]
    sign = items["sign-in"]
    assert sign["outcome"] == "unknown"
    assert sign["time_s"] == 150 and sign["cost_usd"] == 3.0
    assert items["reset"]["latest"] is True and sign["latest"] is False


def test_inside_a_work_item_rows_group_under_a_flow_pass_with_its_state_time_and_cost() -> None:
    with _DB():
        _seed()
        passes = _items()["sign-in"]["passes"]
    assert [(one["flow"], one["pass"], one["state"]) for one in passes] == [("qa", 1, "passed"), ("qa", 2, "passed")]
    assert passes[0]["time_s"] == 126 and passes[0]["cost_usd"] == 2.0
    assert passes[1]["time_s"] == 55 and passes[1]["cost_usd"] == 1.0


def test_a_node_that_runs_twice_has_two_rows() -> None:
    with _DB():
        _seed()
        timeline = activity.timeline(RUN)
        passes = _items()["sign-in"]["passes"]
    assert [row["node"] for row in timeline["rows"]] == ["qa-story"] * 3
    kinds = [entry["kind"] for one in passes for entry in one["entries"] if entry["kind"] == "turn"]
    assert kinds == ["turn", "turn"]


def test_a_run_of_successful_steps_folds_to_one_entry_with_the_count_and_the_time() -> None:
    with _DB():
        _seed()
        entries = _items()["sign-in"]["passes"][0]["entries"]
    folds = [entry for entry in entries if entry["kind"] == "steps"]
    assert [(entry["count"], entry["time_s"]) for entry in folds] == [(2, 11), (1, 8)]
    assert [step["name"] for step in folds[0]["steps"]] == ["lint", "build"]


def test_a_failed_step_stands_as_its_own_entry_between_the_folds() -> None:
    with _DB():
        _seed()
        entries = _items()["sign-in"]["passes"][0]["entries"]
    order = [entry["kind"] for entry in entries]
    assert order.index("failed") == order.index("steps") + 1
    assert order[order.index("failed") + 1] == "steps"
    failed = next(entry for entry in entries if entry["kind"] == "failed")
    assert (failed["name"], failed["result"], failed["duration_s"]) == ("test", "2 tests failed", 7)


def test_a_gate_a_retry_and_a_failed_step_each_have_their_own_entry_with_name_time_and_result() -> None:
    with _DB():
        _seed()
        entries = _items()["sign-in"]["passes"][0]["entries"]
    by_kind = {entry["kind"]: entry for entry in entries if entry["kind"] in ("gate", "retry", "failed")}
    assert set(by_kind) == {"gate", "retry", "failed"}
    assert (by_kind["gate"]["name"], by_kind["gate"]["node"], by_kind["gate"]["duration_s"]) == ("operator gate", "resolve", 30)
    assert by_kind["gate"]["result"] == "escalation #1: docs block · answered"
    assert (by_kind["retry"]["name"], by_kind["retry"]["ts"]) == ("backend retry", BASE + 40)
    assert by_kind["retry"]["result"] == "qa-story turn retried after 30s, attempt 2"
    assert len({entry["key"] for entry in by_kind.values()}) == 3


def test_a_churn_alert_has_its_own_entry_derived_from_the_stored_spans(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_CHURN_REPEATS", "3")
    with _DB():
        _seed()
        _polls()
        entries = _items()["reset"]["passes"][0]["entries"]
    churn = [entry for entry in entries if entry["kind"] == "churn"]
    assert [(entry["name"], entry["result"]) for entry in churn] == [("churn alert", "poll repeated 3 times with the same labels")]


def test_retries_and_churn_alerts_come_back_from_the_stored_spans_after_a_restart(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GROOM_CHURN_REPEATS", "3")
    with _DB():
        _seed()
        _polls()
        before = activity.timeline(RUN)["items"]
        store.reset()
        after = activity.timeline(RUN)["items"]
    kinds = {entry["kind"] for item in after for one in item["passes"] for entry in one["entries"]}
    assert {"retry", "churn"} <= kinds
    assert after == before


def test_the_running_turn_is_the_last_entry_of_its_pass_marked_running() -> None:
    live = {"001-00009-qa-story": [{"key": "001-00009-qa-story:0", "slug": "001-00009-qa-story", "ts": BASE + 1500, "node": "qa-story", "parent": "", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Working."}}}]}
    with _DB():
        _seed()
        timeline = activity.timeline(RUN, live)
    reset = next(item for item in timeline["items"] if item["work_id"] == "reset")
    last = reset["passes"][-1]
    assert last["entries"][-1]["kind"] == "running" and last["state"] == "running"
    assert reset["running"] is True
    row = next(row for row in timeline["rows"] if row["status"] == "running")
    assert (row["work_id"], row["flow"], row["pass"]) == ("", "", 0)


def test_a_run_with_no_work_items_has_one_unnamed_item_holding_its_flow_passes() -> None:
    with _DB():
        store.insert_spans([span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1), *_pass("a", "qa", BASE + 10, "", [("lint", 5, "UNSET")], turn=(100, 2.0))])
        items = activity.timeline(RUN)["items"]
    assert [item["work_id"] for item in items] == [""]
    assert [(one["flow"], one["pass"]) for one in items[0]["passes"]] == [("qa", 1)]


def test_a_heading_adds_up_to_the_overviews_figures_for_that_work_item_and_flow() -> None:
    from groom import overview

    with _DB():
        _seed()
        shown = overview.run_overview(RUN)
        items = activity.timeline(RUN)["items"]
    rows = {row["work_id"]: row for row in shown["items"]["rows"]}
    for item in items:
        assert item["time_s"] == rows[item["work_id"]]["seconds"]
        assert item["cost_usd"] == rows[item["work_id"]]["cost_usd"]
    flow = next(row for row in shown["flows"] if row["name"] == "qa")
    passes = [one for item in items for one in item["passes"] if one["flow"] == "qa"]
    assert sum(one["time_s"] for one in passes) == pytest.approx(flow["time_s"])
    assert sum(one["cost_usd"] or 0 for one in passes) == pytest.approx(flow["cost_usd"])


def _interleaved(run: str = RUN, shared: bool = True) -> None:
    spans = [span("r1", "t1", "", "coder", "run:coder", BASE, 9000, {}, 1, run)]
    plan = [("a1", "alpha", 0), ("b1", "beta", 600), ("a2", "alpha", 1200), ("b2", "beta", 1800), ("a3", "alpha", 2400)]
    for number, (tag, work_id, offset) in enumerate(plan, start=1):
        slug = "001-00001-dev-plan" if shared else f"001-0000{number}-dev-plan"
        spans += _pass(tag, "dev", BASE + 10 + offset, work_id, [("lint", 5, "UNSET")], turn=(100, 1.0), slug=slug)
    for one in spans:
        one["run_id"] = run
    store.insert_spans(spans)


def test_two_work_items_each_count_their_passes_from_first() -> None:
    with _DB():
        _interleaved()
        items = _items()
    assert [(one["flow"], one["pass"]) for one in items["alpha"]["passes"]] == [("dev", 1), ("dev", 2), ("dev", 3)]
    assert [(one["flow"], one["pass"]) for one in items["beta"]["passes"]] == [("dev", 1), ("dev", 2)]


def test_passes_never_skip_or_reorder_in_display_order_even_when_a_visit_slug_repeats_across_passes() -> None:
    with _DB():
        _interleaved()
        shown = activity.timeline(RUN)["items"]
    for item in shown:
        numbers = [one["pass"] for one in item["passes"] if one["flow"] == "dev"]
        assert numbers == list(range(1, len(numbers) + 1))
        stamps = [one["first_ts"] for one in item["passes"]]
        assert stamps == sorted(stamps)


def test_a_run_with_no_work_items_counts_each_flow_across_the_run() -> None:
    with _DB():
        spans = [span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1)]
        spans += _pass("a", "qa", BASE + 10, "", [("lint", 5, "UNSET")], turn=(10, 1.0))
        spans += _pass("b", "qa", BASE + 300, "", [("lint", 5, "UNSET")], turn=(10, 1.0))
        store.insert_spans(spans)
        items = activity.timeline(RUN)["items"]
    assert [one["pass"] for one in items[0]["passes"]] == [1, 2]


def test_the_turn_readers_head_shows_the_number_of_the_heading_the_turn_sits_under() -> None:
    with _DB():
        _interleaved(shared=False)
        timeline = activity.timeline(RUN)
        heading = {entry["slug"]: (one["flow"], one["pass"]) for item in timeline["items"] for one in item["passes"] for entry in one["entries"] if entry["kind"] == "turn"}
        rows = timeline["rows"]
        heads = {}
        for row in rows:
            held = {row["slug"]: [{"key": row["slug"] + ":0", "slug": row["slug"], "ts": row["started_ts"], "node": row["node"], "parent": "", "update": {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "x"}}}]}
            heads[row["slug"]] = activity.turn(RUN, row["slug"], held)["head"]
    assert len(rows) == 5 and all((head["flow"], head["pass"]) == heading[slug] for slug, head in heads.items())


SHARED = "001-00001-qa-story"


def _resumed(kept: tuple[str, ...] = ("s-one", "s-two")) -> None:
    spans = [span("r1", "t1", "", "coder", "run:coder", BASE, 9000, {}, 1)]
    spans += _pass("a1", "dev", BASE + 10, "alpha", [("lint", 5, "UNSET")], turn=(100, 1.0), slug=SHARED, session="s-one")
    spans += _pass("a2", "dev", BASE + 1210, "alpha", [("lint", 5, "UNSET")], turn=(150, 2.5), slug=SHARED, session="s-two")
    store.insert_spans(spans)
    for session, at, offset, text in (("s-one", 19, 50, "the first visit says this"), ("s-two", 1219, 1250, "the second visit says this")):
        if session not in kept:
            continue
        _write(turns.transcripts_root() / RUN / f"{SHARED}__{session}" / "transcript.jsonl", [_claude(offset, "assistant", text)])
        store.insert_turns([{"run_id": RUN, "node": "qa-story", "session_id": session, "generation": 1, "seq": 1, "ts": BASE + at, "path": f"{RUN}/{SHARED}__{session}"}])


def _said(key: str) -> list[str]:
    return [entry["text"] for entry in activity.turn(RUN, key)["entries"]]


def test_a_slug_a_resumed_pass_repeats_gives_two_rows_each_under_its_own_heading() -> None:
    with _DB():
        _resumed()
        timeline = activity.timeline(RUN)
    rows = timeline["rows"]
    assert len(rows) == 2 and rows[0]["slug"] == SHARED and rows[1]["slug"].startswith(SHARED + "~")
    assert [(row["flow"], row["pass"], row["cost_usd"], row["duration_s"]) for row in rows] == [("dev", 1, 1.0, 100), ("dev", 2, 2.5, 150)]
    shown = [[entry["slug"] for entry in one["entries"] if entry["kind"] == "turn"] for one in timeline["items"][0]["passes"]]
    assert shown == [[rows[0]["slug"]], [rows[1]["slug"]]]


def test_a_retry_inside_one_visit_stays_one_row_with_its_attempts_summed() -> None:
    with _DB():
        spans = [span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1)]
        spans += _pass("a", "dev", BASE + 10, "alpha", [], turn=(100, 1.0), slug=SHARED)
        again = span("a-again", "t1", "a-agent", "qa-story", "agent_turn", BASE + 140, 60, _attrs("alpha", model="m", total_cost_usd=0.5, duration_ms=60000, **{"workhorse.visit.slug": SHARED}), 1)
        again["profile_cost_usd"] = 0.5
        store.insert_spans(spans + [again])
        rows = activity.timeline(RUN)["rows"]
    assert [(row["slug"], row["cost_usd"], row["duration_s"]) for row in rows] == [(SHARED, 1.5, 160)]


def test_each_of_two_rows_sharing_a_slug_reads_only_its_own_records() -> None:
    with _DB():
        _resumed()
        first, second = (row["slug"] for row in activity.timeline(RUN)["rows"])
        said = (_said(first), _said(second))
    assert said == (["the first visit says this"], ["the second visit says this"])


def test_a_visit_whose_record_the_archive_did_not_keep_is_not_matched_and_shows_no_other_visits_content() -> None:
    with _DB():
        _resumed(kept=("s-two",))
        rows = activity.timeline(RUN)["rows"]
        first, second = rows[0]["slug"], rows[1]["slug"]
        body = activity.turn(RUN, first)
        later = _said(second)
    assert [row["matched"] for row in rows] == [False, True]
    assert body["entries"] == [] and body["head"]["matched"] is False
    assert later == ["the second visit says this"]


def test_the_rows_under_a_pass_add_up_to_its_heading_on_a_repeated_slug_fixture() -> None:
    with _DB():
        _resumed()
        timeline = activity.timeline(RUN)
    by_slug = {row["slug"]: row for row in timeline["rows"]}
    for one in timeline["items"][0]["passes"]:
        mine = [by_slug[entry["slug"]] for entry in one["entries"] if entry["kind"] == "turn"]
        assert sum(row["cost_usd"] for row in mine) == pytest.approx(one["cost_usd"])
        assert sum(row["duration_s"] for row in mine) == pytest.approx(one["time_s"] - 5)


def test_a_row_key_stays_the_same_across_two_reads() -> None:
    with _DB():
        _resumed()
        first = [row["slug"] for row in activity.timeline(RUN)["rows"]]
        again = [row["slug"] for row in activity.timeline(RUN)["rows"]]
    assert first == again and len(set(first)) == 2


def test_a_suffixed_key_with_no_archive_rows_and_no_files_reads_as_unmatched() -> None:
    with _DB():
        _resumed(kept=())
        first, second = (row["slug"] for row in activity.timeline(RUN)["rows"])
        bodies = [activity.turn(RUN, key) for key in (first, second)]
    assert second.startswith(SHARED + "~")
    assert [(body["entries"], body["head"]["matched"]) for body in bodies] == [([], False), ([], False)]
