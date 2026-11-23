"""The open Overview refreshes its figures in place, in a real browser, and asks the server for nothing between commits."""
from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _post_metric,
    _post_turn,
    _seconds_in,
    teardown_module,  # noqa: F401
)
from test_run_clock_dynamic import _pick, _run

FLOW_TABLE = "Time and cost per flow"
LIVE_TICK_WAIT_MS = 6500


@contextmanager
def _isolated_run(run: str) -> Iterator[str]:
    from groom import state

    try:
        with _run(run) as seeded:
            yield seeded
    finally:
        state.RUNS.pop(run, None)


def _overview_fetches(page, run: str) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if request.url.endswith(f"/api/run/{run}/overview") else None)
    return seen


def _api_requests(page) -> list[str]:
    seen: list[str] = []
    page.on("request", lambda request: seen.append(request.url) if "/api/" in request.url else None)
    return seen


def _age_of_the_last_turn(page) -> int:
    text = page.locator("#detail-cost-tile").inner_text()
    found = re.search(r",\s*(.+?)\s+ago", text)
    assert found, text
    return _seconds_in(found[1])


def test_a_committed_turn_refreshes_cost_coverage_and_tree_with_one_fetch_and_a_beat_fetches_nothing():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-one") as run:
        page = _open(live)
        try:
            fetches = _overview_fetches(page, run)
            _pick(page, run)
            panel = page.get_by_role("tabpanel")
            table = page.get_by_role("table", name=FLOW_TABLE)
            expect(panel).to_contain_text("$3.50")
            expect(panel).to_contain_text("2 of 4 turns priced")
            expect(table).not_to_contain_text("$1.00")
            settled = len(fetches)
            assert settled >= 1

            _post_metric(live, "workhorse.run.heartbeat", 1, run=run, workflow="coder", node="lint")
            expect(table.locator("tr.cur")).to_contain_text("lint")
            page.wait_for_timeout(LIVE_TICK_WAIT_MS)
            assert len(fetches) == settled

            _post_turn(live, "00000000000000c1", usd=1.0, run=run, node="dev")
            expect(panel).to_contain_text("$4.50")
            expect(panel).to_contain_text("3 of 5 turns priced")
            expect(table).to_contain_text("$1.00")
            page.wait_for_timeout(1500)
            assert len(fetches) == settled + 1
        finally:
            page.close()


def test_the_last_turn_age_counts_up_every_second_and_asks_the_server_for_nothing():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-tick") as run:
        page = _open(live)
        try:
            _pick(page, run)
            _post_turn(live, "00000000000000c2", usd=1.0, run=run, node="dev")
            expect(page.get_by_role("tabpanel")).to_contain_text("$4.50")
            requests = _api_requests(page)
            readings = []
            for _ in range(4):
                readings.append(_age_of_the_last_turn(page))
                page.wait_for_timeout(1100)
            assert readings == sorted(set(readings))
            assert readings[-1] - readings[0] >= 3
            assert requests == []
        finally:
            page.close()


def test_a_refresh_keeps_expanded_rows_expanded_and_collapsed_rows_collapsed():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-open") as run:
        page = _open(live)
        try:
            _pick(page, run)
            expect(page.get_by_role("tabpanel")).to_contain_text("$3.50")
            table = page.get_by_role("table", name=FLOW_TABLE)
            table.get_by_role("button", name="Expand work").click()
            expect(table.get_by_role("button", name="Collapse work")).to_have_count(1)
            table.get_by_role("button", name="Collapse coder").click()
            expect(table.get_by_role("button", name="Expand coder")).to_have_count(1)

            _post_turn(live, "00000000000000c3", usd=1.0, run=run, node="dev")
            expect(page.locator("#detail-cost-tile")).to_contain_text("$4.50")
            expect(table.get_by_role("button", name="Expand coder")).to_have_count(1)
            expect(table.get_by_role("button", name="Collapse coder")).to_have_count(0)

            table.get_by_role("button", name="Expand coder").click()
            expect(table.get_by_role("button", name="Collapse work")).to_have_count(1)
            expect(table.get_by_role("button", name="Expand work")).to_have_count(0)
        finally:
            page.close()


def test_a_held_refresh_keeps_the_old_figures_on_screen_with_no_busy_state():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-held") as run:
        page = _open(live)
        held: list = []
        try:
            _pick(page, run)
            panel = page.get_by_role("tabpanel")
            expect(panel).to_contain_text("$3.50")
            page.evaluate(
                "() => { window.__tile = document.querySelector('#detail-cost-tile');"
                " window.__tile.dataset.mark = 'kept'; }"
            )
            page.route(f"**/api/run/{run}/overview", lambda route: held.append(route))
            _post_turn(live, "00000000000000c4", usd=1.0, run=run, node="dev")
            deadline = 20
            while not held and deadline:
                page.wait_for_timeout(250)
                deadline -= 1
            assert len(held) == 1

            expect(page.locator("#detail-cost-tile")).to_contain_text("$3.50")
            expect(panel.locator("[aria-busy='true']")).to_have_count(0)
            expect(panel.get_by_text("Reading this run")).to_have_count(0)

            held[0].continue_()
            expect(page.locator("#detail-cost-tile")).to_contain_text("$4.50")
            assert page.evaluate("() => window.__tile.isConnected && window.__tile.dataset.mark") == "kept"
            expect(panel.locator("[aria-busy='true']")).to_have_count(0)
        finally:
            for route in held[1:]:
                route.continue_()
            page.close()


def test_a_refresh_that_fails_keeps_the_old_figures_and_catches_up_with_no_new_telemetry():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-retry") as run:
        page = _open(live)
        answers: list[int] = []

        def answer(route) -> None:
            answers.append(1)
            if len(answers) == 1:
                route.fulfill(status=503, body="{}", content_type="application/json")
            else:
                route.continue_()

        try:
            _pick(page, run)
            panel = page.get_by_role("tabpanel")
            expect(panel).to_contain_text("$3.50")
            page.route(f"**/api/run/{run}/overview", answer)
            _post_turn(live, "00000000000000c7", usd=1.0, run=run, node="dev")
            deadline = 40
            while not answers and deadline:
                page.wait_for_timeout(250)
                deadline -= 1
            assert len(answers) == 1

            expect(page.locator("#detail-cost-tile")).to_contain_text("$3.50")
            expect(panel.locator("[role='alert']")).to_have_count(0)
            expect(page.locator("#detail-cost-tile")).to_contain_text("$4.50", timeout=15000)
            assert len(answers) == 2
        finally:
            page.close()


def test_a_refresh_keeps_the_scroll_position_of_the_open_overview_while_held_and_after():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-scroll") as run:
        page = _open(live)
        held: list = []
        try:
            page.set_viewport_size({"width": 1400, "height": 330})
            _pick(page, run)
            panel = page.get_by_role("tabpanel")
            expect(panel).to_contain_text("$3.50")
            _post_metric(live, "workhorse.run.heartbeat", 1, run=run, workflow="coder", node="dev")
            expect(panel.locator(".now")).to_contain_text("dev")
            page.wait_for_timeout(LIVE_TICK_WAIT_MS)
            scroller = panel.locator(".ov").first
            scroller.evaluate("el => { el.scrollTop = 120; }")
            assert scroller.evaluate("el => el.scrollTop") == 120
            mark = "() => document.querySelector('#detail-wall-clock').getBoundingClientRect().top"
            placed = page.evaluate(mark)
            page.route(f"**/api/run/{run}/overview", lambda route: held.append(route))
            _post_turn(live, "00000000000000c8", usd=1.0, run=run, node="dev")
            deadline = 20
            while not held and deadline:
                page.wait_for_timeout(250)
                deadline -= 1
            assert len(held) == 1

            assert scroller.evaluate("el => el.scrollTop") == 120
            assert abs(page.evaluate(mark) - placed) <= 1
            held[0].continue_()
            expect(page.locator("#detail-cost-tile")).to_contain_text("$4.50")
            assert scroller.evaluate("el => el.scrollTop") > 0
            assert abs(page.evaluate(mark) - placed) <= 1
        finally:
            for route in held[1:]:
                route.continue_()
            page.close()


def test_a_finished_node_loses_the_running_mark_and_the_next_node_gains_it():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-mark") as run:
        page = _open(live)
        try:
            _pick(page, run)
            table = page.get_by_role("table", name=FLOW_TABLE)
            expect(page.get_by_role("tabpanel")).to_contain_text("$3.50")
            marks = table.locator(".chip", has_text=re.compile("running", re.I))

            _post_metric(live, "workhorse.node.active", 1, run=run, workflow="coder", node="dev")
            expect(table.locator("tr.cur")).to_contain_text("dev")
            expect(marks).to_have_count(1)

            _post_turn(live, "00000000000000c5", usd=1.0, run=run, node="dev")
            expect(page.locator("#detail-cost-tile")).to_contain_text("$4.50")
            _post_metric(live, "workhorse.node.active", 0, run=run, workflow="coder", node="dev")
            expect(table.locator("tr.cur")).to_have_count(0)
            expect(marks).to_have_count(0)
            _post_metric(live, "workhorse.node.active", 1, run=run, workflow="coder", node="lint")

            expect(table.locator("tr.cur")).to_contain_text("lint")
            expect(table.locator("tr.cur")).not_to_contain_text("dev")
            expect(marks).to_have_count(1)
            expect(table.locator("tr", has_text="dev").locator(".chip", has_text=re.compile("running", re.I))).to_have_count(0)
        finally:
            page.close()


def test_no_live_region_wraps_or_holds_the_figures():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("refresh-aria") as run:
        page = _open(live)
        try:
            _pick(page, run)
            expect(page.get_by_role("tabpanel")).to_contain_text("$3.50")
            _post_turn(live, "00000000000000c6", usd=1.0, run=run, node="dev")
            expect(page.locator("#detail-cost-tile")).to_contain_text("$4.50")
            announced = page.evaluate(
                """() => {
                  const live = '[aria-live]:not([aria-live=off]),[role=status],[role=log],[role=alert],[role=timer]';
                  const figures = [
                    '#detail-cost-tile', '#detail-turns-tile',
                    'table[aria-label="Time and cost per flow"]',
                  ];
                  return figures.map((selector) => {
                    const el = document.querySelector(selector);
                    return [selector, !el ? 'missing' : (el.closest(live) || el.querySelector(live)) ? 'live' : 'quiet'];
                  });
                }"""
            )
            assert announced == [
                ["#detail-cost-tile", "quiet"],
                ["#detail-turns-tile", "quiet"],
                ['table[aria-label="Time and cost per flow"]', "quiet"],
            ]
        finally:
            page.close()
