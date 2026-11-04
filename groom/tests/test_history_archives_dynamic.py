from __future__ import annotations

import json
import re
import shutil
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _scan,
    teardown_module,  # noqa: F401
)
from test_archive_history import _without_summary
from test_history import seed
from test_history_dynamic import _clear, _failing_until_cleared, _history_page, _open_history, _table, _totals
from test_history_filters_dynamic import _choose, _options
from test_history_open_dynamic import _read_the_failure_and_retry, AXE, DETAIL, LONG_REPO, LONG_RUN

from groom import archive, history, store, turns

DAY = 86400.0
EVERYTHING = "Everything, archives included"
TABLE = "Runs that ended, newest first"
READING = "Reading the archive for the first time. This takes a few seconds once, then it is instant."


def _telemetry(run: str) -> Path:
    folder = archive.exact_dir(run)
    assert folder is not None
    return folder / archive.TELEMETRY_FILE


def _wipe() -> None:
    _clear()
    with store.STORE.writing() as conn:
        conn.execute("DELETE FROM run_summary")
    shutil.rmtree(archive.archives_root(), ignore_errors=True)
    shutil.rmtree(turns.transcripts_root(), ignore_errors=True)


@contextmanager
def _archived(*runs: str, summarized: bool = True) -> Iterator[float]:
    now = time.time()
    _wipe()
    for index, run in enumerate(runs):
        seed(run, now - (60 + index) * DAY)
        destination, _ = archive.archive_run(store.run_bounds()[run], now)
        assert destination is not None
        if not summarized:
            _without_summary(destination)
    try:
        yield now
    finally:
        _wipe()


def _everything(live, handler=None):
    page = _open_history(live, handler)
    page.wait_for_selector("#history table.ht, #history .empty-big", timeout=10000)
    _choose(page, "Range", EVERYTHING)
    return page


def _archive_page(live, run: str):
    page = _everything(live)
    page.wait_for_selector(f"#history tr.hrow:has-text('{run}')", timeout=10000)
    return page


def _open_archive(page, run: str) -> None:
    page.locator("#history tr.hrow", has_text=run).first.click()


def test_the_range_filter_offers_everything_archives_included_and_it_is_operable_by_keyboard() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a"):
        page = _history_page(live)
        try:
            options = _options(page, "Range")
            hidden = page.locator("#history tr.hrow").count()
            box = page.get_by_role("combobox", name="Range")
            box.focus()
            page.keyboard.press("ArrowDown")
            page.keyboard.press("ArrowDown")
            page.wait_for_selector("#history tr.hrow:has-text('arch-a')", timeout=10000)
            chosen = box.evaluate("(el) => el.options[el.selectedIndex].text")
        finally:
            page.close()
    assert options[-1] == EVERYTHING
    assert hidden == 0
    assert chosen == EVERYTHING


def test_everything_lists_an_archived_run_from_its_stored_summary_with_an_archived_chip_and_the_scope_says_everything() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a"):
        page = _archive_page(live, "arch-a")
        try:
            row = _table(page, TABLE)[0]
            scope = page.locator("#history .h-top").inner_text()
            totals = _totals(page)
            chip = page.locator("#history tr.hrow .who .chip").inner_text().lower()
        finally:
            page.close()
    assert row[0] == "coder arch-a archived"
    assert chip == "archived"
    assert "everything" in scope.lower()
    assert totals[0] == "1 run"


def test_an_archived_run_in_the_narrowed_list_wears_the_archived_chip_on_its_first_line() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a"):
        page = _archive_page(live, "arch-a")
        try:
            _open_archive(page, "arch-a")
            page.wait_for_selector("#history .row .line1 .chip", timeout=10000)
            chip = page.locator("#history .row .line1 .chip").inner_text().lower()
        finally:
            page.close()
    assert chip == "archived"


def test_an_older_archive_reads_its_summary_while_the_table_says_so_and_the_row_fills_in_without_a_reload() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a", summarized=False):
        history.discover_archives()
        page = _archive_page(live, "arch-a")
        try:
            before = page.locator("#history tr.hrow").first.inner_text()
            totals_before = _totals(page)
            history.compute_archive("arch-a")
            page.wait_for_function("() => !document.querySelector('#history tr.hrow').innerText.includes('reading its summary')", timeout=15000)
            after = _table(page, TABLE)[0]
            totals_after = " ".join(_totals(page))
        finally:
            page.close()
    assert "reading its summary" in before
    assert "1 summary still being read" in " ".join(totals_before)
    assert after[0] == "coder arch-a archived"
    assert after[6].startswith("$3.00")
    assert "still being read" not in totals_after


def test_an_archive_nobody_has_summarized_yet_is_counted_as_unlisted_until_its_row_exists() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a", summarized=False):
        page = _everything(live)
        try:
            body = page.evaluate("() => fetch('/api/history?archives=1').then((r) => r.json())")
            plain = page.evaluate("() => fetch('/api/history').then((r) => r.json())")
        finally:
            page.close()
    assert body["unlisted"] == 1
    assert plain["unlisted"] == 0


def test_an_unreadable_summary_shows_the_row_with_no_figures_says_so_and_retry_now_asks_again() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a", summarized=False):
        history.discover_archives()
        _telemetry("arch-a").write_text("not a manifest\n", encoding="utf-8")
        history.compute_archive("arch-a")
        page = _archive_page(live, "arch-a")
        try:
            row = page.locator("#history tr.hrow").first
            text = row.inner_text()
            totals = " ".join(_totals(page))
            row.get_by_role("button", name=re.compile("^Retry")).click()
            page.wait_for_function("() => document.querySelector('#history tr.hrow').innerText.includes('reading its summary')", timeout=15000)
            stored = history.stored("arch-a")
            state = stored["state"] if stored else None
        finally:
            page.close()
    assert "could not be read" in text
    assert "1 summary could not be read" in totals
    assert state == history.PENDING


def test_the_first_open_of_an_archive_says_it_is_reading_then_shows_the_overview_with_no_files_diff_or_activity_tab() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    held: list = []
    with _archived("arch-a"):
        page = _archive_page(live, "arch-a")
        page.route("**/api/archive/**", lambda route: held.append(route))
        try:
            _open_archive(page, "arch-a")
            page.wait_for_selector(f"{DETAIL} .loading", timeout=10000)
            reading = page.locator(f"{DETAIL} .loading").inner_text().strip()
            problems_during = page.locator(f"{DETAIL} button.problems-link, {DETAIL} [data-problems]").count()
            held[0].continue_()
            page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)
            tabs = page.locator(f"{DETAIL} [role=tab]").all_inner_texts()
            head = page.locator(f"{DETAIL} .detail-head").inner_text().lower()
            attention = page.locator(f"{DETAIL} #detail-attention-tile").inner_text()
            links = page.locator(f"{DETAIL} #detail-attention-tile button").count()
        finally:
            page.close()
    assert reading == READING
    assert problems_during == 0
    assert [tab.split()[0] for tab in tabs] == ["Overview"]
    assert "archived" in head
    assert "problem" in attention
    assert links == 0


def test_a_later_open_of_an_archive_shows_no_reading_state_and_the_overview_comes_in_under_two_seconds() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a"):
        first = _archive_page(live, "arch-a")
        try:
            _open_archive(first, "arch-a")
            first.wait_for_selector(f"{DETAIL} .ov", timeout=30000)
        finally:
            first.close()
        page = _archive_page(live, "arch-a")
        try:
            seen: list[str] = []
            page.on("framenavigated", lambda frame: None)
            began = time.perf_counter()
            _open_archive(page, "arch-a")
            page.wait_for_selector(f"{DETAIL} .ov", timeout=10000)
            took = time.perf_counter() - began
            seen = page.locator(f"{DETAIL} .loading").all_inner_texts()
        finally:
            page.close()
    assert seen == []
    assert took < 2.0


def test_an_archive_whose_files_are_gone_keeps_its_row_and_shows_the_stored_tiles_and_facts() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a"):
        _telemetry("arch-a").unlink()
        page = _archive_page(live, "arch-a")
        try:
            rows = page.locator("#history tr.hrow").count()
            _open_archive(page, "arch-a")
            page.wait_for_selector(f"{DETAIL} .side-state", timeout=15000)
            state = page.locator(f"{DETAIL} .side-state").inner_text()
            tiles = page.locator(f"{DETAIL} .kpis").inner_text().lower()
            facts = page.locator(f"{DETAIL} .pair").inner_text().lower()
            tabs = page.locator(f"{DETAIL} [role=tab]").count()
        finally:
            page.close()
    assert rows == 1
    assert "This archive's files are gone" in state
    assert "The cost and times below come from the run's stored summary. Activity and transcripts cannot be read." in state
    assert "$3.00" in tiles and "wall" in tiles and "agent turns" in tiles and "attention" in tiles
    assert "arch-a" in facts and "branch" in facts
    assert tabs == 1


def test_an_archive_that_cannot_be_opened_says_so_in_the_detail_and_a_retry_shows_the_overview() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    answers, answer = _failing_until_cleared()
    with _archived("arch-a"):
        page = _archive_page(live, "arch-a")
        page.route("**/api/archive/**", answer)
        try:
            _open_archive(page, "arch-a")
            text, rows = _read_the_failure_and_retry(page, answers)
            page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)
        finally:
            page.close()
    assert "This archive could not be read" in text
    assert "Its row in the list comes from the stored summary." in text
    assert rows == 1


def test_a_live_ended_run_still_shows_its_overview_and_activity_tabs_when_everything_is_chosen() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    from test_history_open_dynamic import _ended

    with _ended():
        page = _everything(live)
        try:
            page.locator("#history tr.hrow", has_text="hist-a").first.click()
            page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)
            tabs = [tab.split()[0] for tab in page.locator(f"{DETAIL} [role=tab]").all_inner_texts()]
            chips = page.locator("#history tr.hrow .who .chip").count()
        finally:
            page.close()
    assert tabs == ["Overview", "Activity"]
    assert chips == 0


def test_the_archive_surfaces_pass_an_axe_scan() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a", "arch-b"):
        _telemetry("arch-b").unlink()
        page = _archive_page(live, "arch-a")
        try:
            page.add_script_tag(path=str(AXE))
            table = _scan(page)
            _open_archive(page, "arch-a")
            page.wait_for_selector(f"{DETAIL} .ov", timeout=30000)
            overview = _scan(page)
            page.locator("#history .row", has_text="arch-b").click()
            page.wait_for_selector(f"{DETAIL} .side-state", timeout=15000)
            gone = _scan(page)
            page.route("**/api/archive/**", lambda route: route.fulfill(status=500, body="no"))
            page.locator("#history .row", has_text="arch-a").click()
            page.wait_for_selector(f"{DETAIL} .retry-overview", timeout=15000)
            failed = _scan(page)
        finally:
            page.close()
    assert not failed, json.dumps(failed, indent=1)
    assert not table, json.dumps(table, indent=1)
    assert not overview, json.dumps(overview, indent=1)
    assert not gone, json.dumps(gone, indent=1)


def test_a_long_run_id_and_repo_label_keep_the_archived_row_inside_the_table_and_the_narrowed_list() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    now = time.time()
    _wipe()
    seed(LONG_RUN, now - 60 * DAY)
    store.run_bounds()
    with store.STORE.writing() as conn:
        conn.execute("UPDATE spans SET repo = ? WHERE run_id = ?", (LONG_REPO, LONG_RUN))
    archive.archive_run(store.run_bounds()[LONG_RUN], now)
    try:
        page = _archive_page(live, LONG_RUN[:12])
        try:
            wide = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            chip = page.locator("#history tr.hrow .who .chip").bounding_box()
            _open_archive(page, LONG_RUN[:12])
            page.wait_for_selector("#history .row .line1 .chip", timeout=10000)
            box = page.locator("#history .row").first.evaluate("(el) => [el.scrollWidth, el.clientWidth]")
        finally:
            page.close()
    finally:
        _wipe()
    assert not wide
    assert chip is not None and chip["width"] > 0
    assert box[0] <= box[1]


def test_a_slow_answer_for_the_old_range_does_not_replace_the_list_of_the_range_chosen_after_it() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    held: list = []
    with _archived("arch-a"):
        page = _everything(live)
        try:
            page.wait_for_selector("#history tr.hrow:has-text('arch-a')", timeout=10000)
            page.route("**/api/history", lambda route: held.append(route))
            _choose(page, "Range", "Last 30 days")
            page.wait_for_function("() => true")
            while not held:
                page.wait_for_timeout(50)
            _choose(page, "Range", EVERYTHING)
            page.wait_for_selector("#history tr.hrow:has-text('arch-a')", timeout=10000)
            held[0].continue_()
            page.wait_for_timeout(800)
            shown = page.locator("#history tr.hrow:has-text('arch-a')").count()
        finally:
            page.close()
    assert shown == 1


def test_an_archive_that_gets_its_row_later_appears_in_the_table_without_a_reload() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a", summarized=False):
        page = _everything(live)
        try:
            page.wait_for_timeout(500)
            history.discover_archives()
            page.wait_for_selector("#history tr.hrow:has-text('arch-a')", timeout=15000)
            rows = page.locator("#history tr.hrow").count()
        finally:
            page.close()
    assert rows == 1


def test_pressing_enter_on_retry_now_asks_again_and_does_not_open_the_run() -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived("arch-a", summarized=False):
        history.discover_archives()
        _telemetry("arch-a").write_text("not a manifest\n", encoding="utf-8")
        history.compute_archive("arch-a")
        page = _archive_page(live, "arch-a")
        try:
            page.get_by_role("button", name=re.compile("^Retry")).focus()
            page.keyboard.press("Enter")
            page.wait_for_function("() => document.querySelector('#history tr.hrow').innerText.includes('reading its summary')", timeout=15000)
            opened = page.locator(f"{DETAIL} .detail-head").count()
            selected = page.locator("#history .selected, #history [aria-current=true]").count()
        finally:
            page.close()
    assert opened == 0
    assert selected == 0
