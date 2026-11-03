from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_history import seed

TABLE = "Runs that ended, newest first"
HEADERS = ["Run", "Repo", "Ending", "Ended ▾", "Active", "Wall", "Cost", "Items", "Turns", "Gates", "Problems"]
WHEN = re.compile(r"^[A-Z][a-z]{2} \d{1,2} \d\d:\d\d$")


def _row(run: str, age_h: float, **fields: object) -> dict:
    ended = time.time() - age_h * 3600
    return {
        "run_id": run, "workflow": "coder", "repo": "acme", "branch": "main", "state": "ready",
        "ending": "success", "ended_ts": ended, "last_ts": ended, "active_s": 3600.0,
        "wall_s": 7200.0, "cost_usd": 10.0, "priced_turns": 4, "turns": 4, "items_done": 2,
        "items_total": 2, "gates": 0, "problems": 0, **fields,
    }


def _clear() -> None:
    from groom import store
    from groom.store import STORE

    with STORE.writing() as conn:
        conn.execute("DELETE FROM run_summary")
    for run in ("hist-a", "hist-b"):
        store.delete_run_telemetry(run)


@contextmanager
def _history(*rows: dict) -> Iterator[None]:
    from groom import history

    _clear()
    for row in rows:
        history._write(row)
    try:
        yield
    finally:
        _clear()


def _open_history(live, handler=None):
    page = live.browser.new_page(viewport={"width": 1400, "height": 900})
    if handler is not None:
        page.route("**/api/history", handler)
    page.goto(live.url(), wait_until="load")
    page.wait_for_selector("#runs-list .row", timeout=15000)
    page.click('.act-btn[data-mode="history"]')
    return page


def _history_page(live):
    page = _open_history(live)
    page.wait_for_selector("#history table.ht, #history .empty-big", timeout=10000)
    return page


_CELLS = """(rows) => rows.map((row) => Array.from(row.querySelectorAll("td")).map((cell, at) => at === 0
  ? Array.from(cell.querySelectorAll(".who > *")).map((part) => part.textContent.trim()).join(" ")
  : cell.textContent.replace(/\\s+/g, " ").trim()))"""


def _table(page, name: str) -> list[list[str]]:
    return page.get_by_role("table", name=name).locator("tbody tr").evaluate_all(_CELLS)


def _totals(page) -> list[str]:
    return [" ".join(cell.split()) for cell in page.locator("#history .h-sum span").all_inner_texts()]


def test_the_rail_shows_runs_history_attendant_dispatch_and_settings_in_that_order():
    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        names = page.locator("#activitybar .act-btn").evaluate_all("(buttons) => buttons.map((b) => b.getAttribute('aria-label'))")
    finally:
        page.close()
    assert names == ["Runs", "History", "Attendant", "Dispatch", "Settings"]


def test_selecting_history_shows_the_ended_runs_newest_end_time_first_under_every_column():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(_row("hist-old", 30), _row("hist-new", 2), _row("hist-mid", 10)):
        page = _history_page(live)
        try:
            headers = page.get_by_role("table", name=TABLE).locator("thead th").all_inner_texts()
            runs = [row[0] for row in _table(page, TABLE)]
            heading = page.locator("#history-pane .pane-head").inner_text()
            pressed = page.locator('.act-btn[data-mode="history"]').get_attribute("aria-pressed")
        finally:
            page.close()
    assert [text.strip().lower() for text in headers] == [name.lower() for name in HEADERS]
    assert [run.split()[-1] for run in runs] == ["hist-new", "hist-mid", "hist-old"]
    assert "history" in heading.lower()
    assert pressed == "true"


def test_a_row_reads_the_workflow_run_repo_ending_end_time_active_wall_cost_items_turns_gates_and_problems():
    live = _live()
    assert live is not None, _UNAVAILABLE
    row = _row("hist-a", 3, active_s=68 * 3600 + 7 * 60.0, wall_s=13 * 3600.0, cost_usd=148.02, priced_turns=41, turns=41, items_done=2, items_total=2, gates=1, problems=4, ending="failed")
    with _history(row):
        page = _history_page(live)
        try:
            cells = _table(page, TABLE)[0]
        finally:
            page.close()
    assert cells[0] == "coder hist-a"
    assert cells[1] == "acme@main"
    assert cells[2] == "failed"
    assert WHEN.match(cells[3]), cells[3]
    assert cells[4:] == ["68h 07m", "13h", "$148.02", "2", "41", "1", "4"]


def test_every_ending_is_written_in_words():
    live = _live()
    assert live is not None, _UNAVAILABLE
    endings = {"success": "success", "gave-up": "gave up", "failed": "failed", "interrupted": "interrupted", "crashed": "crashed", "none": "no ending recorded"}
    rows = [_row(f"hist-{key}", index + 1, ending=key) for index, key in enumerate(endings)]
    with _history(*rows):
        page = _history_page(live)
        try:
            read = {row[0].split()[-1]: row[2] for row in _table(page, TABLE)}
        finally:
            page.close()
    assert read == {f"hist-{key}": words for key, words in endings.items()}


def test_a_cost_missing_some_turns_shows_the_priced_count_and_an_estimate_carries_est():
    live = _live()
    assert live is not None, _UNAVAILABLE
    partly = _row("hist-partly", 1, cost_usd=677.67, priced_turns=153, turns=163)
    estimated = _row("hist-est", 2, cost_usd=None, est_usd=31.2, priced_turns=0, turns=121)
    with _history(partly, estimated):
        page = _history_page(live)
        try:
            cost = {row[0].split()[-1]: row[6] for row in _table(page, TABLE)}
            title = page.locator("#history tbody tr", has_text="hist-partly").locator(".cov").get_attribute("title")
        finally:
            page.close()
    assert cost == {"hist-partly": "$677.67153/163", "hist-est": "est $31.20"}
    assert title == "10 turns reported no cost"


def test_items_read_n_of_m_when_some_did_not_finish_and_the_bare_count_when_all_did():
    live = _live()
    assert live is not None, _UNAVAILABLE
    rows = [_row("hist-short", 1, items_done=1, items_total=2), _row("hist-all", 2, items_done=6, items_total=6), _row("hist-none", 3, items_done=None, items_total=None)]
    with _history(*rows):
        page = _history_page(live)
        try:
            items = {row[0].split()[-1]: row[7] for row in _table(page, TABLE)}
        finally:
            page.close()
    assert items == {"hist-short": "1 of 2", "hist-all": "6", "hist-none": "—"}


def test_the_totals_show_runs_money_active_time_and_successes_and_omit_a_clause_that_is_zero():
    live = _live()
    assert live is not None, _UNAVAILABLE
    plain = [_row("hist-a", 1, cost_usd=100.0, active_s=3600.0), _row("hist-b", 2, cost_usd=50.5, active_s=1800.0, ending="failed")]
    with _history(*plain):
        page = _history_page(live)
        try:
            first = _totals(page)
        finally:
            page.close()
    messy = plain + [_row("hist-est", 3, cost_usd=None, est_usd=31.2, priced_turns=0, turns=9, active_s=600.0), _row("hist-part", 4, cost_usd=20.0, priced_turns=1, turns=2, active_s=0.0)]
    with _history(*messy):
        page = _history_page(live)
        try:
            second = _totals(page)
        finally:
            page.close()
    assert first == ["2 runs", "$150.50 spent", "1h 30m active", "1 of 2 ended in success"]
    assert second == ["4 runs", "$201.70 spent, $31.20 of it an estimate, 1 run partly priced", "1h 40m active", "3 of 4 ended in success"]


def test_an_ended_run_with_no_summary_reads_reading_its_summary_stays_out_of_the_sums_and_fills_in_without_a_reload():
    from groom import history

    live = _live()
    assert live is not None, _UNAVAILABLE
    _clear()
    now = time.time()
    seed("hist-a", now - 3600, costs=(4.0,))
    history.discover(now)
    page = _history_page(live)
    try:
        pending = _table(page, TABLE)[0]
        before = _totals(page)
        marker = page.evaluate("window.__marker = 'same page'")
        history.compute("hist-a", now)
        page.wait_for_selector("#history tbody tr td .chip", timeout=15000)
        filled = _table(page, TABLE)[0]
        after = _totals(page)
        same = page.evaluate("window.__marker")
    finally:
        page.close()
        _clear()
    assert pending[0] == "coder hist-a"
    assert "reading its summary" in pending[2]
    assert WHEN.match(pending[3])
    assert pending[4:] == ["—"] * 7
    assert before == ["1 run", "$0.00 spent, 1 summary still being read", "0m active"]
    assert filled[2] == "success"
    assert filled[6] == "$4.00"
    assert after[0] == "1 run" and "still being read" not in " ".join(after)
    assert marker == same == "same page"


def test_the_pane_shows_a_reading_state_that_clears_when_the_table_appears():
    live = _live()
    assert live is not None, _UNAVAILABLE
    held: list = []
    with _history(_row("hist-a", 1)):
        page = _open_history(live, lambda route: held.append(route))
        try:
            page.wait_for_selector("#history .loading", timeout=10000)
            state = page.locator("#history .loading")
            text = state.inner_text()
            role, busy = state.get_attribute("role"), state.get_attribute("aria-busy")
            held[0].continue_()
            page.wait_for_selector("#history table.ht", timeout=10000)
            remaining = page.locator("#history .loading").count()
        finally:
            page.close()
    assert "Reading the runs that ended" in text
    assert (role, busy) == ("status", "true")
    assert remaining == 0


def _failing_until_cleared():
    answers = {"fail": True}

    def answer(route) -> None:
        if answers["fail"]:
            route.fulfill(status=500, body="no")
        else:
            route.continue_()

    return answers, answer


def test_a_failed_read_says_history_could_not_be_read_offers_a_retry_and_a_retry_that_succeeds_shows_the_table():
    live = _live()
    assert live is not None, _UNAVAILABLE
    answers, answer = _failing_until_cleared()

    with _history(_row("hist-a", 1)):
        page = _open_history(live, answer)
        try:
            page.wait_for_selector("#history .side-state", timeout=10000)
            message = page.locator("#history .side-state").inner_text()
            answers["fail"] = False
            page.get_by_role("button", name="Retry now").click()
            page.wait_for_selector("#history table.ht", timeout=10000)
            page.click('.act-btn[data-mode="runs"]')
            runs_visible = page.locator("#runs-pane").is_visible()
        finally:
            page.close()
    assert "History could not be read" in message
    assert "The Runs tab still works" in message
    assert runs_visible


def test_with_no_ended_runs_the_pane_says_so_with_the_totals_at_zero():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history():
        page = _history_page(live)
        try:
            message = page.locator("#history .empty-big").inner_text()
            totals = _totals(page)
        finally:
            page.close()
    assert message == "No run has ended in the last 30 days."
    assert totals == ["0 runs", "$0.00 spent", "0m active"]


def test_a_run_that_is_alive_is_not_listed_in_the_browser():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(_row("run-running", 1, ending=""), _row("hist-a", 2)):
        page = _history_page(live)
        try:
            runs = [row[0].split()[-1] for row in _table(page, TABLE)]
        finally:
            page.close()
    assert runs == ["hist-a"]


def test_runs_attendant_dispatch_and_settings_open_as_they_did():
    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _open(live)
    try:
        shown = {}
        for mode in ("history", "attend", "dispatch", "settings", "runs"):
            page.click(f'.act-btn[data-mode="{mode}"]')
            shown[mode] = [pane for pane in ("runs", "history", "attend", "dispatch", "settings") if page.locator(f"#{pane}-pane").is_visible()]
    finally:
        page.close()
    assert shown == {mode: [mode] for mode in ("history", "attend", "dispatch", "settings", "runs")}


def test_the_table_and_its_rows_have_a_role_a_name_and_keyboard_operation():
    live = _live()
    assert live is not None, _UNAVAILABLE
    rows = [_row("hist-a", 1), _row("hist-b", 2), _row("hist-c", 3)]
    with _history(*rows):
        page = _history_page(live)
        try:
            table = page.get_by_role("table", name=TABLE)
            names = page.get_by_role("columnheader").all_inner_texts()
            tabs = page.locator("#history tbody tr").evaluate_all("(rows) => rows.map((r) => r.tabIndex)")
            page.locator("#history tbody tr").first.focus()
            page.keyboard.press("ArrowDown")
            second = page.evaluate("document.activeElement.dataset.run")
            page.keyboard.press("End")
            last = page.evaluate("document.activeElement.dataset.run")
            page.keyboard.press("Home")
            first = page.evaluate("document.activeElement.dataset.run")
            count = table.count()
        finally:
            page.close()
    assert count == 1
    assert len(names) == len(HEADERS)
    assert tabs == [0, -1, -1]
    assert (second, last, first) == ("hist-b", "hist-c", "hist-a")


def test_the_history_pane_has_no_accessibility_violations():
    live = _live()
    assert live is not None, _UNAVAILABLE
    rows = [_row("hist-a", 1, ending="failed", problems=3, cost_usd=20.0, priced_turns=1, turns=2), _row("hist-b", 2, ending="none", cost_usd=None, est_usd=3.0, priced_turns=0)]
    with _history(*rows):
        page = _open_history(live)
        try:
            page.wait_for_selector("#history table.ht", timeout=10000)
            page.add_script_tag(path=str(Path(__file__).resolve().parent / "vendor" / "axe.min.js"))
            violations = _scan(page)
        finally:
            page.close()
    assert not violations, json.dumps(violations, indent=1)


def test_a_long_repo_or_run_name_cuts_off_with_its_full_text_kept_and_every_column_stays_in_view():
    live = _live()
    assert live is not None, _UNAVAILABLE
    run = "hist-a-" + "r" * 60
    branch = "worktree-agent-" + "b" * 40
    with _history(_row(run, 3, branch=branch, problems=4)):
        page = _history_page(live)
        try:
            cells = page.locator("table.ht tbody tr").first.locator("td")
            repo_title = cells.nth(1).get_attribute("title")
            run_title = cells.nth(0).get_attribute("title")
            right = cells.last.evaluate("(cell) => cell.getBoundingClientRect().right")
            width = page.evaluate("document.documentElement.clientWidth")
        finally:
            page.close()
    assert repo_title == f"acme@{branch}"
    assert run_title == run
    assert right <= width
