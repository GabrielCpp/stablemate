"""A run row shows its cost, active time and items done in a real browser, and the figures follow the telemetry with no reload."""
from __future__ import annotations

import re

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _post_metric,
    _post_turn,
    teardown_module,  # noqa: F401
)
from test_figures_refresh_dynamic import _isolated_run
from test_run_clock_dynamic import _pick

ACTIVE = r"\d+(\.\d+)?(ms|s|m|h)\s+active"


def _row(page, run: str):
    return page.locator("#runs-list .row", has_text=run)


def test_a_row_shows_cost_with_its_coverage_active_time_and_items():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("fig-priced", spans=[]) as run:
        page = _open(live)
        try:
            _post_turn(live, "00000000000000d1", usd=1.5, run=run, node="dev", progress="1/3")
            _post_turn(live, "00000000000000d2", usd=None, run=run, node="dev")
            row = _row(page, run)
            expect(row).to_contain_text("$1.50")
            expect(row).to_contain_text("1/2 priced")
            expect(row).to_contain_text("1/3 items")
            expect(row).to_contain_text(re.compile(ACTIVE))
        finally:
            page.close()


def test_a_backend_with_no_cost_says_so_in_place_of_a_dollar_figure():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("fig-nocost", spans=[]) as run:
        page = _open(live)
        try:
            _post_turn(live, "00000000000000d3", usd=None, run=run, node="dev")
            row = _row(page, run)
            expect(row).to_contain_text("no cost reported")
            expect(row).not_to_contain_text("$")
            expect(row).not_to_contain_text("priced")
        finally:
            page.close()


def test_the_narrowed_column_keeps_the_figures_and_drops_the_word_priced():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("fig-narrow", spans=[]) as run:
        page = _open(live)
        try:
            _post_turn(live, "00000000000000d4", usd=2.5, run=run, node="dev", progress="2/4")
            row = _row(page, run)
            expect(row).to_contain_text("1/1 priced")
            _pick(page, run)
            expect(page.locator("#detail")).to_be_visible()
            expect(row).to_contain_text("$2.50")
            expect(row).to_contain_text("1/1")
            expect(row).to_contain_text("2/4 items")
            expect(row).not_to_contain_text("priced")
        finally:
            page.close()


def test_a_run_with_no_finished_node_shows_no_cost_and_no_items_then_fills_them_in():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("fig-fresh", spans=[]) as run:
        page = _open(live)
        try:
            _post_metric(live, "workhorse.run.heartbeat", 1, run=run, workflow="coder", node="dev")
            row = _row(page, run)
            expect(row).to_contain_text("no cost yet")
            expect(row).not_to_contain_text("$")
            expect(row).not_to_contain_text("items")

            _post_turn(live, "00000000000000d5", usd=0.75, run=run, node="dev", progress="1/2")
            expect(row).to_contain_text("$0.75")
            expect(row).to_contain_text("1/2 items")
            expect(row).not_to_contain_text("no cost yet")
        finally:
            page.close()


def test_the_figures_follow_new_telemetry_with_no_reload():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("fig-live", spans=[]) as run:
        page = _open(live)
        try:
            page.evaluate("window.__same_page = true")
            _post_turn(live, "00000000000000d6", usd=1.0, run=run, node="dev")
            row = _row(page, run)
            expect(row).to_contain_text("$1.00")
            expect(row).to_contain_text("1/1 priced")

            _post_turn(live, "00000000000000d7", usd=2.0, run=run, node="dev")
            expect(row).to_contain_text("$3.00")
            expect(row).to_contain_text("2/2 priced")
            assert page.evaluate("window.__same_page") is True
        finally:
            page.close()


def test_j_k_and_the_filter_work_on_rows_with_figures():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("fig-nav-a", spans=[]) as first, _isolated_run("fig-nav-b", spans=[]) as second:
        page = _open(live)
        try:
            _post_turn(live, "00000000000000d8", usd=1.0, run=first, node="dev")
            _post_turn(live, "00000000000000d9", usd=2.0, run=second, node="dev")
            page.get_by_role("searchbox", name="Filter runs").fill("fig-nav")
            rows = page.locator("#runs-list .row")
            expect(rows).to_have_count(2)
            expect(_row(page, first)).to_contain_text("$1.00")
            expect(_row(page, second)).to_contain_text("$2.00")

            _pick(page, first)
            selected = page.locator("#runs-list .row.selected")
            expect(selected).to_contain_text(first)
            page.keyboard.press("j")
            expect(selected).to_contain_text("fig-nav-")
            expect(selected).not_to_contain_text(first)
            expect(selected).to_contain_text("$")
            page.keyboard.press("k")
            expect(selected).to_contain_text(first)
            expect(selected).to_contain_text("$1.00")
        finally:
            page.close()
