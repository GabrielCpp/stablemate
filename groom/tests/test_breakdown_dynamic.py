"""The cost breakdown switcher, measured on the page the operator gets."""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _ingest_aged,
    _live,
    _open,
    _post_turn,
    _scan,
    _seconds_in,
    teardown_module,  # noqa: F401
)

RUN = "run-items"
WORKFLOW = "builder"
CONTAINER = "builder12345"

NODES = (("build", 150.0, 0.1), ("review", 50.0, 5.0))


def _span(span_id: str, run: str, parent: str, node: str, name: str, at: float, seconds: float, attrs: dict) -> dict:
    return {
        "span_id": span_id, "trace_id": run, "parent_id": parent, "run_id": run, "workflow": WORKFLOW,
        "repo": "acme", "branch": "main", "node": node, "name": name, "run_dir": "",
        "start_ts": at, "end_ts": at + seconds, "status": "OK", "attrs": attrs,
    }


def _history(ok: int, failed: int) -> list[str]:
    from groom import store

    runs = []
    spans = []
    for kind, count, terminal, seconds in (("ok", ok, "terminal", 100.0), ("bad", failed, "fail", 1000.0)):
        for index in range(count):
            run = f"{WORKFLOW}-{kind}-{index}"
            runs.append(run)
            spans.append(_span(f"{run}-root", run, "", f"run:{WORKFLOW}", f"run:{WORKFLOW}", 1000.0, 900.0, {"workhorse.terminal": terminal}))
            for node, _, _ in NODES:
                turn = {"backend": "claude", "duration_ms": seconds * 1000, "total_cost_usd": 1.0}
                spans.append(_span(f"{run}-{node}", run, "", node, "agent_turn", 1000.0, seconds, turn))
    store.insert_spans(spans)
    return runs


def _items_run(items: tuple[str, ...]) -> None:
    from groom import store

    now = time.time()
    spans = [_span("it-state", RUN, "", "work", "work", now - 900, 800.0, {"workhorse.span_kind": "state", "workhorse.depth": 0})]
    at = now - 880
    for position, item in enumerate(items):
        for node, seconds, cost in NODES:
            tag = {"work_id": item, "progress": f"{position}/{len(items)}"}
            node_id = f"it-{position}-{node}"
            spans.append(_span(node_id, RUN, "it-state", node, node, at, seconds, {"workhorse.depth": 1, **tag}))
            turn = {"backend": "claude", "duration_ms": seconds * 1000, "total_cost_usd": cost, **tag}
            spans.append(_span(f"{node_id}-t", RUN, node_id, node, "agent_turn", at, seconds, turn))
            at += seconds + 5
    store.insert_spans(spans)


@contextmanager
def _seeded(*, ok: int = 5, failed: int = 6, items: tuple[str, ...] = ("alpha", "beta"), running: float = 0.0) -> Iterator[None]:
    from groom import norms, state, store
    from groom.models import WorkflowState

    runs = _history(ok, failed)
    _items_run(items)
    norms.reset()
    state.upsert_workflow(
        CONTAINER, name="builder-acme", workflow_type=WORKFLOW, repo_name="acme", repo_branch="main",
        current_node="build", activity="building", run_id=RUN, state=WorkflowState.RUNNING, native=True,
    )
    if running:
        _ingest_aged(RUN, "build", {"workhorse.node.active": 1.0, "workhorse.node.elapsed_s": running}, age=30.0)
    try:
        yield
    finally:
        state.WORKFLOWS.pop(CONTAINER, None)
        norms.reset()
        for run in (RUN, *runs):
            store.delete_run_telemetry(run)


def _pick_run(page, run: str) -> None:
    page.locator("#runs-list .row", has_text=run).first.click()


def _view(page, name: str):
    return page.get_by_role("group", name="Breakdown view").get_by_role("button", name=name, exact=True)


def _sort(page, name: str):
    return page.get_by_role("group", name="Sort by").get_by_role("button", name=name, exact=True)


def _rows(page, table: str) -> list[list[str]]:
    body = page.get_by_role("table", name=table).locator("tbody tr")
    return [[cell.strip() for cell in row.locator("td").all_inner_texts()] for row in body.all()]


def _node_rows(page) -> dict[str, list[str]]:
    return {row[0]: row for row in _rows(page, "Time and cost per node") if "RUNNING" not in row[0].upper()}


def test_the_node_view_compares_each_mean_with_the_median_of_successful_runs_only():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded(ok=5, failed=6):
        page = _open(live)
        try:
            _pick_run(page, RUN)
            _view(page, "By node").click()
            table = page.get_by_role("table", name="Time and cost per node")
            expect(table.get_by_role("columnheader", name="vs median of 5")).to_have_count(1)
            build = _node_rows(page)["build"]
            assert "+50% longer" in build[5], build
            kinds = [row[1] for row in _node_rows(page).values()]
            assert kinds == ["agent", "agent"], kinds
            assert not _scan(page)
        finally:
            page.close()


def test_with_fewer_than_five_comparable_runs_the_comparison_is_blank_and_says_why():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded(ok=4, failed=6):
        page = _open(live)
        try:
            _pick_run(page, RUN)
            _view(page, "By node").click()
            table = page.get_by_role("table", name="Time and cost per node")
            expect(table.get_by_role("columnheader", name="vs median: 4 runs, under five")).to_have_count(1)
            for row in _node_rows(page).values():
                assert row[5] == "—", row
        finally:
            page.close()


def test_the_view_and_sort_survive_a_tab_round_trip_and_a_live_refresh_and_reset_on_another_run():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded():
        page = _open(live)
        try:
            _pick_run(page, RUN)
            expect(_view(page, "By flow")).to_have_attribute("aria-pressed", "true")
            expect(_sort(page, "Time")).to_have_attribute("aria-pressed", "true")
            _view(page, "By node").click()
            _sort(page, "Cost").click()
            page.get_by_role("tab", name="Activity").click()
            page.get_by_role("tab", name="Overview").click()
            expect(_view(page, "By node")).to_have_attribute("aria-pressed", "true")
            expect(_sort(page, "Cost")).to_have_attribute("aria-pressed", "true")
            expect(page.get_by_role("table", name="Time and cost per node")).to_be_visible()
            turns = int(page.locator("#detail-turns-tile .vv").inner_text())
            _post_turn(live, "00000000000000c1", usd=1.0, run=RUN, workflow=WORKFLOW, node="build")
            expect(page.locator("#detail-turns-tile .vv")).to_have_text(str(turns + 1), timeout=15000)
            expect(_view(page, "By node")).to_have_attribute("aria-pressed", "true")
            expect(_sort(page, "Cost")).to_have_attribute("aria-pressed", "true")
            expect(page.get_by_role("table", name="Time and cost per node")).to_be_visible()
            _pick_run(page, "run-blocked")
            expect(_view(page, "By flow")).to_have_attribute("aria-pressed", "true")
            expect(_sort(page, "Time")).to_have_attribute("aria-pressed", "true")
        finally:
            page.close()


def test_sorting_by_time_or_cost_reorders_the_node_rows_without_a_fetch():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded():
        page = _open(live)
        try:
            _pick_run(page, RUN)
            _view(page, "By node").click()
            expect(page.get_by_role("table", name="Time and cost per node")).to_be_visible()
            assert list(_node_rows(page)) == ["build", "review"]
            requests: list[str] = []
            page.on("request", lambda request: requests.append(request.url))
            _sort(page, "Cost").click()
            expect(_sort(page, "Cost")).to_have_attribute("aria-pressed", "true")
            assert list(_node_rows(page)) == ["review", "build"]
            _sort(page, "Time").click()
            assert list(_node_rows(page)) == ["build", "review"]
            assert not [url for url in requests if "/api/" in url], requests
        finally:
            page.close()


def test_the_work_item_view_exists_only_for_a_run_with_items_and_marks_the_open_one():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded(running=30.0):
        page = _open(live)
        try:
            _pick_run(page, "run-blocked")
            expect(_view(page, "By node")).to_have_count(1)
            expect(_view(page, "By work item")).to_have_count(0)
            _pick_run(page, RUN)
            _view(page, "By work item").click()
            expect(page.get_by_role("table", name="Time and cost per work item")).to_be_visible()
            expect(_sort(page, "Time")).to_have_count(0)
            rows = {row[0]: row for row in _rows(page, "Time and cost per work item")}
            assert "OPEN" in rows["beta"][4].upper(), rows
            assert "DONE" in rows["alpha"][4].upper(), rows
            assert rows["alpha"][1].startswith("1 "), rows
            assert rows["Total"][3] == "$10.20", rows
            _view(page, "By flow").click()
            flow = page.get_by_role("table", name="Time and cost per flow")
            expect(flow.get_by_role("row", name=re.compile(r"Collapse builder")).first).to_contain_text("$10.20")
        finally:
            page.close()


def test_the_view_switch_and_sort_work_from_the_keyboard_and_pass_axe():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded():
        page = _open(live)
        try:
            _pick_run(page, RUN)
            _view(page, "By node").focus()
            page.keyboard.press("Enter")
            expect(_view(page, "By node")).to_have_attribute("aria-pressed", "true")
            _sort(page, "Cost").focus()
            page.keyboard.press("Space")
            expect(_sort(page, "Cost")).to_have_attribute("aria-pressed", "true")
            assert not _scan(page)
            _view(page, "By work item").focus()
            page.keyboard.press("Enter")
            expect(page.get_by_role("table", name="Time and cost per work item")).to_be_visible()
            assert not _scan(page)
        finally:
            page.close()


def test_the_running_node_counts_on_the_clock_of_the_row_and_the_strip_in_the_node_view():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded(running=600.0):
        page = _open(live)
        try:
            _pick_run(page, RUN)
            page.get_by_role("group", name="Where the run is now").wait_for()
            _view(page, "By node").click()
            deadline = time.time() + 6
            readings: dict[str, int] = {}
            while time.time() < deadline:
                values = page.evaluate(
                    """() => {
                      const row = document.querySelector('#runs-list .row[aria-current="true"] .mini');
                      const lead = document.querySelector('[aria-label="Where the run is now"] > div:nth-child(2) .v2');
                      const mark = document.querySelector('table.tt tr.cur .chip');
                      const cell = document.querySelector('table.tt tr.cur td:nth-child(4)');
                      return [row, lead, mark, cell].map((el) => (el ? el.innerText : ''));
                    }"""
                )
                readings = {
                    "row": _seconds_in(values[0].split("·")[0]),
                    "strip": _seconds_in(values[1]),
                    "mark": _seconds_in(values[2]),
                    "cell": _seconds_in(values[3]),
                }
                if len(set(readings.values())) == 1:
                    break
                time.sleep(0.2)
            assert len(set(readings.values())) == 1 and 630 <= readings["strip"] <= 640, readings
        finally:
            page.close()


def test_the_strip_calls_an_agent_node_with_no_turn_gauge_a_node_between_turns_and_agrees_with_the_table():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _seeded(ok=5, failed=6, running=30.0):
        page = _open(live)
        try:
            _pick_run(page, RUN)
            strip = page.get_by_role("group", name="Where the run is now")
            expect(strip).to_contain_text("Between turns")
            expect(strip).to_contain_text("a turn here usually takes 1m 40s")
            text = strip.inner_text()
            assert "In step" not in text and "no agent in a step" not in text, text
            _view(page, "By node").click()
            table = page.get_by_role("table", name="Time and cost per node")
            expect(table.get_by_role("columnheader", name="vs median of 5")).to_have_count(1)
            assert _node_rows(page)["build"][1] == "agent"
        finally:
            page.close()
