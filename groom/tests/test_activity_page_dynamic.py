"""The Activity tab of a long run opens on its newest work items and shows the older ones when asked, measured on the page the operator gets."""
from __future__ import annotations

import time

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    teardown_module,  # noqa: F401
)
from test_activity_tab_dynamic import _open_activity, _pick, _run
from test_run_clock import STATE, span

ITEMS = 25
SECTIONS = "#detail-panel .tl > .tl-sec"


def _items(run: str) -> None:
    from groom import store

    base = time.time() - 9000.0
    spans = [
        span("r1", "t1", "", "coder", "run:coder", base, 8900, {}, 1, run),
        span("s1", "t1", "r1", "work", "work", base + 1, 8800, STATE, 1, run),
    ]
    for number in range(ITEMS):
        at = base + 10 + number * 300
        work = {"work_id": f"story-{number:02d}"}
        spans.append(span(f"n{number}", "t1", "s1", "dev", "dev", at, 200, {"workhorse.depth": 2} | work, 1, run))
        spans.append(span(f"a{number}", "t1", f"n{number}", "dev", "agent_turn", at + 1, 100, work | {"model": "m", "total_cost_usd": 0.5, "backend": "claude", "session.id": f"s{number}"}, 1, run))
    store.insert_spans(spans)


def test_a_long_run_opens_on_its_newest_work_items_and_shows_the_older_ones_when_asked(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-older", tmp_path, turns=False) as run:
        _items(run)
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(SECTIONS)).to_have_count(20)
            expect(page.locator(SECTIONS).first).to_contain_text("story-05")
            expect(page.locator(SECTIONS).last).to_contain_text("story-24")
            note = page.locator("#detail-panel .tl-older")
            expect(note).to_contain_text("5 older work items are not shown.")
            page.get_by_role("button", name="Show older work items").click()
            expect(page.locator(SECTIONS)).to_have_count(ITEMS)
            expect(page.locator(SECTIONS).first).to_contain_text("story-00")
            expect(note).to_have_count(0)
        finally:
            page.close()


def test_picking_an_older_work_item_reads_the_whole_run(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-whole", tmp_path, turns=False) as run:
        _items(run)
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(SECTIONS)).to_have_count(20)
            page.get_by_role("combobox", name="Work item").select_option("story-24")
            expect(page.locator(SECTIONS)).to_have_count(1)
            page.get_by_role("combobox", name="Work item").select_option("")
            expect(page.locator(SECTIONS)).to_have_count(ITEMS)
        finally:
            page.close()
