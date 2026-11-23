"""The overview tiles state their figures in a real browser: cost per finished item, a labelled estimate, and the tiles appearing with the first finished node."""
from __future__ import annotations

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _overview_payload,
    _post_metric,
    _post_turn,
    _scan,
    teardown_module,  # noqa: F401
)
from test_figures_refresh_dynamic import _isolated_run
from test_run_clock_dynamic import _pick


def test_the_items_tile_gives_no_per_item_figure_until_an_item_finishes_then_divides_by_finished_items():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("tiles-items", spans=[]) as run:
        page = _open(live)
        try:
            _post_turn(live, "00000000000000e1", usd=1.0, run=run, node="dev", progress="0/3")
            _pick(page, run)
            items = page.locator("#detail-items-tile")
            expect(items).to_contain_text("0 of 3")
            expect(items).to_contain_text("none finished yet")
            expect(items).not_to_contain_text("per finished item")
            _post_turn(live, "00000000000000e2", usd=2.0, run=run, node="dev", progress="2/3")
            expect(items).to_contain_text("2 of 3", timeout=15000)
            expect(items).to_contain_text("$1.50 per finished item")
            assert not _scan(page)
        finally:
            page.close()


def test_a_live_backend_with_no_cost_shows_an_estimate_labelled_at_list_price():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    priced = {"model": "claude-sonnet-5", "usage.input_tokens": 1_000_000, "usage.output_tokens": 0}
    with _isolated_run("tiles-estimate", spans=[]) as run:
        page = _open(live)
        try:
            _post_turn(live, "00000000000000e3", usd=None, run=run, node="dev", progress="1/2", attrs=priced)
            _pick(page, run)
            estimate = _overview_payload(live, run)["figures"]["est_usd"]
            assert estimate and estimate > 0, estimate
            cost = page.locator("#detail-cost-tile")
            expect(cost).to_contain_text("reports no cost")
            expect(cost).to_contain_text(f"est ${estimate:.2f} at list price")
            expect(page.locator("#detail-items-tile")).to_contain_text("no cost per item without a price")
            assert not _scan(page)
        finally:
            page.close()


def test_the_tiles_appear_in_place_when_the_first_node_finishes():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _isolated_run("tiles-first", spans=[]) as run:
        page = _open(live)
        try:
            _post_metric(live, "workhorse.run.heartbeat", 1, run=run, workflow="coder", node="dev")
            _pick(page, run)
            panel = page.get_by_role("tabpanel")
            expect(panel).to_contain_text("Figures appear when the first node finishes")
            expect(page.locator(".kpi")).to_have_count(0)
            expect(panel).not_to_contain_text("problem")
            _post_turn(live, "00000000000000e4", usd=0.75, run=run, node="dev", progress="1/2")
            expect(page.locator(".kpi")).to_have_count(5, timeout=15000)
            expect(page.locator("#detail-cost-tile")).to_contain_text("$0.75")
            expect(panel).not_to_contain_text("Figures appear when the first node finishes")
            assert not _scan(page)
        finally:
            page.close()
