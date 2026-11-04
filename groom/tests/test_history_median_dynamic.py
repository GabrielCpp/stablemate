from __future__ import annotations

import json
import time
from collections.abc import Iterator
from contextlib import contextmanager

from playwright.sync_api import expect
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _scan,
    teardown_module,  # noqa: F401
)
from test_history import refresh
from test_history_dynamic import TABLE, _clear, _history, _history_page, _open_history, _row, _table, _totals
from test_history_filters_dynamic import _api_requests_after_the_table, _choose
from test_history_open_dynamic import AXE, DETAIL, LONG_REPO, LONG_RUN, _opened, _ready, _rich

from groom import history

TILE = f"{DETAIL} #detail-items-tile"
NODES = "Time and cost per node"
MINUS = "−"


@contextmanager
def _judged(others: tuple[float, ...] = (2.0,) * 5, per_item: float = 6.0, speed: float = 0.5, terminal: str = "terminal", progress: str = "2/2", **own: object) -> Iterator[None]:
    now = time.time()
    _clear()
    _rich("hist-a", now - 3 * 3600, terminal, {"progress": progress})
    refresh(now)
    summary = history.stored("hist-a")
    assert summary is not None
    nodes = json.loads(summary["nodes_json"])
    quicker = json.dumps([{**node, "time_s": node["time_s"] * speed} for node in nodes])
    for index, cost in enumerate(others):
        history._write(_row(f"other-{index}", 5 + index, cost_usd=cost * 2, nodes_json=quicker))
    history._write(_row("hist-a", 3, **{"cost_usd": per_item * 2, **own}))
    try:
        yield
    finally:
        _clear()


def _overview(live, view: str | None = None):
    page = _opened(live)
    _ready(page)
    if view:
        page.get_by_role("group", name="Breakdown view").get_by_role("button", name=view, exact=True).click()
    return page


def _node_cells(page) -> dict[str, list[str]]:
    body = page.get_by_role("table", name=NODES).locator("tbody tr")
    return {row[0]: row for row in ([cell.strip() for cell in one.locator("td").all_inner_texts()] for one in body.all())}


def test_the_table_gains_a_column_with_cost_per_item_and_its_signed_percent_from_the_median():
    live = _live()
    assert live is not None, _UNAVAILABLE
    pool = [_row(f"hist-p{index}", 20 + index, cost_usd=4.0) for index in range(5)]
    rows = [
        _row("hist-up", 1, cost_usd=24.0),
        _row("hist-down", 2, cost_usd=2.0),
        _row("hist-failed", 3, cost_usd=18.0, ending="failed", items_done=1),
        _row("hist-none", 4, cost_usd=18.0, items_done=0),
        _row("hist-est", 5, cost_usd=None, est_usd=31.2, priced_turns=0),
        _row("hist-book", 6, workflow="okf-book", cost_usd=9.0),
    ]
    with _history(*pool, *rows):
        page = _history_page(live)
        try:
            header = page.get_by_role("columnheader", name="$/item vs median")
            title = header.get_attribute("title")
            cells = {row[0].split()[-1]: row[8] for row in _table(page, TABLE)}
        finally:
            page.close()
    assert "median of successful runs of the same workflow" in title and "fewer than five" in title
    assert cells["hist-up"] == "$12 +500%"
    assert cells["hist-down"] == f"$1.00 {MINUS}50%"
    assert cells["hist-failed"] == "$18"
    assert cells["hist-none"] == "—"
    assert cells["hist-est"] == "est $16"
    assert cells["hist-book"] == "$4.50"


def test_under_five_comparable_runs_the_table_cell_shows_the_cost_per_item_with_no_difference():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*[_row(f"hist-p{index}", 20 + index, cost_usd=4.0) for index in range(3)], _row("hist-one", 1, cost_usd=24.0)):
        page = _history_page(live)
        try:
            cells = {row[0].split()[-1]: row[8] for row in _table(page, TABLE)}
            marks = page.locator("#history .vs").count()
        finally:
            page.close()
    assert cells["hist-one"] == "$12"
    assert marks == 0


def test_with_a_workflow_filter_the_totals_show_the_median_per_item_and_the_runs_behind_it_without_a_request():
    live = _live()
    assert live is not None, _UNAVAILABLE
    coder = [_row(f"hist-c{index}", 1 + index, cost_usd=cost * 2) for index, cost in enumerate((1.0, 2.0, 3.0, 4.0, 9.0))]
    with _history(*coder, _row("hist-a1", 8, workflow="author", cost_usd=6.0), _row("hist-f", 9, cost_usd=500.0, ending="failed")):
        page = _open_history(live)
        try:
            asked = _api_requests_after_the_table(page)
            every = _totals(page)
            _choose(page, "Workflow", "coder")
            coder_totals = _totals(page)
            cell_title = page.locator("#history .h-sum span").last.get_attribute("title")
            _choose(page, "Workflow", "author")
            author_totals = _totals(page)
            page.wait_for_timeout(300)
        finally:
            page.close()
    assert not [text for text in every if "median" in text]
    assert coder_totals[-1] == "$3.00 median per coder item, 5 comparable runs"
    assert cell_title == "Successful runs of this workflow with a reported cost and a finished item"
    assert author_totals[-1] == "— median per author item: only 1 comparable run, and it takes 5"
    assert not [url for url in asked if "/api/history" in url]


def test_the_totals_median_ignores_the_range_and_the_other_filters():
    live = _live()
    assert live is not None, _UNAVAILABLE
    rows = [_row(f"hist-c{index}", 1 + index * 24 * 6, cost_usd=cost * 2, repo="acme" if index % 2 else "globex") for index, cost in enumerate((1.0, 2.0, 3.0, 4.0, 9.0))]
    with _history(*rows):
        page = _open_history(live)
        try:
            page.wait_for_selector("#history table.ht", timeout=10000)
            _choose(page, "Workflow", "coder")
            _choose(page, "Repo", "acme")
            _choose(page, "Range", "Last 7 days")
            narrowed = _totals(page)
        finally:
            page.close()
    assert narrowed[0] == "1 run"
    assert narrowed[-1] == "$3.00 median per coder item, 5 comparable runs"


def test_the_work_items_tile_shows_cost_per_item_the_signed_percent_and_the_sample_size_in_words():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged():
        page = _overview(live)
        try:
            tile = page.locator(TILE).inner_text()
        finally:
            page.close()
    assert "$6.00 per item +200% vs median of 5 runs" in " ".join(tile.split())


def test_the_tile_of_a_run_with_under_five_comparable_runs_says_how_many_exist_and_that_it_takes_five():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged(others=(2.0, 2.0, 2.0)):
        page = _overview(live)
        try:
            tile = " ".join(page.locator(TILE).inner_text().split())
            phrase = page.locator(TILE + " span[title]").get_attribute("title")
        finally:
            page.close()
    assert "$6.00 per item, no comparison: only 3 other comparable coder runs, and it takes 5" in tile
    assert phrase == "Successful runs of this workflow with a reported cost and a finished item"
    assert "%" not in tile


def test_the_tile_of_a_run_with_no_other_comparable_run_says_none_exists_yet_and_that_it_takes_five():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged(others=()):
        page = _overview(live)
        try:
            tile = " ".join(page.locator(TILE).inner_text().split())
        finally:
            page.close()
    assert "$6.00 per item, no comparison: no other comparable coder run yet, and it takes 5" in tile


def test_a_run_that_did_not_end_in_success_shows_no_comparison_in_the_tile_or_by_node():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged(terminal="fail", ending="failed"):
        page = _overview(live, "By node")
        try:
            tile = " ".join(page.locator(TILE).inner_text().split())
            heading = page.get_by_role("table", name=NODES).locator("thead th").all_inner_texts()
            cells = [row[5] for row in _node_cells(page).values()]
        finally:
            page.close()
    assert "$6.00 per item, not compared: the run failed" in tile
    assert "vs median" in [text.strip().lower() for text in heading]
    assert set(cells) == {"—"}


def test_a_run_with_no_finished_item_shows_no_cost_per_item_in_the_tile():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged(terminal="fail", ending="failed", progress="0/2", items_done=0):
        page = _overview(live)
        try:
            tile = " ".join(page.locator(TILE).inner_text().split())
        finally:
            page.close()
    assert "no item finished, so no cost per item" in tile


def test_an_estimate_run_shows_its_estimate_per_item_in_the_tile_and_is_not_compared():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged(cost_usd=None, est_usd=31.2, priced_turns=0, ending="none", terminal="fail"):
        page = _overview(live)
        try:
            tile = " ".join(page.locator(TILE).inner_text().split())
        finally:
            page.close()
    assert "est $16 per item, not compared: no ending recorded" in tile


def test_by_node_shows_each_agent_nodes_mean_against_its_median_with_the_sample_size_in_the_heading():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _judged():
        page = _overview(live, "By node")
        try:
            table = page.get_by_role("table", name=NODES)
            expect(table.get_by_role("columnheader", name="vs median of 5")).to_have_count(1)
            title = table.get_by_role("columnheader", name="vs median of 5").get_attribute("title")
            cells = _node_cells(page)
            kinds = {name: row[1] for name, row in cells.items()}
            classes = page.get_by_role("table", name=NODES).locator("tbody td:nth-child(6) span[title]").evaluate_all("spans => spans.map(span => span.className)")
        finally:
            page.close()
    assert title == "Mean visit against the same node across successful runs of this workflow"
    compared = [row[5] for name, row in cells.items() if kinds[name] == "agent"]
    assert compared and all(text.endswith("%") and text[0] in "+" + MINUS and "longer" not in text for text in compared), cells
    assert {row[5] for name, row in cells.items() if kinds[name] != "agent"} <= {"—"}
    assert classes and set(classes) == {""}, classes


def test_the_comparison_surfaces_pass_an_axe_scan_and_carry_the_difference_as_text():
    live = _live()
    assert live is not None, _UNAVAILABLE
    pool = [_row(f"hist-p{index}", 20 + index, cost_usd=4.0) for index in range(5)]
    with _history(*pool, _row("hist-up", 1, cost_usd=24.0), _row("hist-down", 2, cost_usd=2.0)):
        page = _history_page(live)
        try:
            page.add_script_tag(path=str(AXE))
            table = _scan(page)
            colored = page.locator("#history .vs").evaluate_all("(els) => els.map((el) => el.textContent.trim())")
        finally:
            page.close()
    with _judged():
        page = _overview(live, "By node")
        try:
            page.add_script_tag(path=str(AXE))
            detail = _scan(page)
        finally:
            page.close()
    assert not table, json.dumps(table, indent=1)
    assert not detail, json.dumps(detail, indent=1)
    assert {f"{MINUS}50%", "+500%"} <= set(colored)


def test_a_long_run_id_and_repo_label_keep_the_comparison_column_in_view_at_one_width():
    live = _live()
    assert live is not None, _UNAVAILABLE
    pool = [_row(f"hist-p{index}", 20 + index, cost_usd=4.0) for index in range(5)]
    with _history(*pool, _row(LONG_RUN, 1, repo=LONG_REPO, cost_usd=24.0), _row("hist-b", 2, cost_usd=231.33, priced_turns=80, turns=81, ending="none", items_done=1, items_total=2)):
        page = _history_page(live)
        try:
            box = "(el) => { const r = el.getBoundingClientRect(); return [Math.round(r.left), Math.round(r.right), Math.round(r.width)]; }"
            cell = page.locator(f'#history tr[data-run="{LONG_RUN}"] td').nth(8)
            holder = page.locator("#history .h-list")
            inside = cell.evaluate(box)[1] <= holder.evaluate(box)[1] + 1
            fits = holder.evaluate("(el) => el.scrollWidth <= el.clientWidth")
            wide = page.locator("table.ht").evaluate(box)[2]
            _choose(page, "Workflow", "coder")
            same = page.locator("table.ht").evaluate(box)[2]
            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        finally:
            page.close()
    assert inside and fits
    assert wide == same
    assert not overflow
