"""The Activity tab of an archived run, measured on the page the operator gets, over a real archive."""
from __future__ import annotations

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
from test_activity_tab_dynamic import _run
from test_history_archives_dynamic import _archive_page, _open_archive, _telemetry, _wipe
from test_history_open_dynamic import AXE, LONG_RUN
from test_run_clock import span

from groom import archive, state, store

DETAIL = "#history-detail"
PANEL = f"{DETAIL} #detail-panel"
LINES = f"{PANEL} .raw .log-line"
TURN_API = "**/api/archive/*/activity/*"
FAILED = "ensure_stack"


@contextmanager
def _archived_activity(tmp: Path, run: str, *, logs: int = 0, samples: int = 0, **given) -> Iterator[str]:
    _wipe()
    with _run(run, tmp, **given) as name:
        at = time.time() - 3200
        broke = span("e1", "t1", "n2", FAILED, FAILED, at, 4, {"error.class": "StackStartFailed", "status_message": "port 5432 is already allocated"}, 1, name)
        store.insert_spans([broke | {"status": "ERROR"}])
        with store.STORE.writing() as conn:
            conn.execute("UPDATE spans SET attrs_json = ? WHERE run_id = ? AND span_id = 'r1'", ('{"workhorse.terminal": "terminal"}', name))
        store.insert_logs([{"run_id": name, "node": "lint", "severity": "INFO", "body": f"line {number}", "ts": at + 10 + number * 0.01} for number in range(logs)])
        store.insert_metrics([{"run_id": name, "name": "workhorse.gas", "ts": at + 20 + number, "value": float(number), "attrs": {"node": "lint"}} for number in range(samples)])
        for container in [key for key, one in state.WORKFLOWS.items() if one.run_id == name]:
            state.WORKFLOWS.pop(container)
        destination, _ = archive.archive_run(store.run_bounds()[name], time.time())
        assert destination is not None
        try:
            yield name
        finally:
            _wipe()


def _opened(live, name: str):
    page = _archive_page(live, name)
    _open_archive(page, name)
    page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)
    return page


def _activity(page) -> None:
    page.locator(f"{DETAIL}").get_by_role("tab", name="Activity").click()
    page.wait_for_selector(f"{PANEL} .feed, {PANEL} .side-state", timeout=10000)


def _drive(tmp_path: Path, run: str, check, *, tab: bool = True, **given) -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived_activity(tmp_path, run, **given) as name:
        page = _opened(live, name)
        try:
            if tab:
                _activity(page)
            check(page, name)
        finally:
            page.close()


def test_an_archived_run_has_the_activity_tab_with_the_timeline_the_filters_and_the_keys_of_an_ended_run(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        names = [text.strip() for text in page.locator(DETAIL).get_by_role("tab").all_inner_texts()]
        assert [text.split()[0] for text in names] == ["Overview", "Activity"], names
        rows = page.locator(f"{PANEL} .tl button.ev")
        expect(rows.first).to_be_visible()
        assert rows.count() >= 2
        chips = page.locator(f"{PANEL} .feedbar [data-filter]").evaluate_all("(els) => els.map((el) => el.dataset.filter)")
        assert {"problems", "steps", "logs", "raw"} <= set(chips), chips
        hints = page.locator(f"{PANEL} .feedbar .hint")
        expect(hints.nth(0)).to_have_text("j k move")
        expect(hints.nth(1)).to_have_text("e next problem")
        rows.nth(0).click()
        expect(rows.nth(0)).to_have_attribute("aria-current", "true")
        page.keyboard.press("j")
        expect(rows.nth(1)).to_have_attribute("aria-current", "true")
        page.keyboard.press("k")
        expect(rows.nth(0)).to_have_attribute("aria-current", "true")

    _drive(tmp_path, "arch-tab", check)


def test_the_overview_problem_count_of_an_archived_run_opens_the_tab_and_both_show_one_number(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        link = page.locator(f"{DETAIL} #detail-problems-link")
        expect(link).to_be_visible()
        counted = int(link.inner_text().split()[0])
        assert counted >= 1
        link.click()
        expect(page.locator(f"{DETAIL} [role=tab][aria-selected=true]")).to_contain_text("Activity")
        page.wait_for_selector(f"{PANEL} .tl button.ev", timeout=10000)
        problems = page.locator(f'{PANEL} .feedbar [data-filter="problems"]')
        expect(problems).to_have_attribute("aria-pressed", "true")
        assert int(problems.locator("b").inner_text()) == counted
        tab = page.locator(f"{DETAIL} [role=tab]", has_text="Activity").inner_text()
        assert str(counted) in tab

    _drive(tmp_path, "arch-problems", check, tab=False)


def test_selecting_a_turn_of_an_archived_run_reads_it_from_the_archive_in_the_reading_pane(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived_activity(tmp_path, "arch-turn") as name:
        page = _opened(live, name)
        asked: list[str] = []
        page.on("request", lambda request: asked.append(request.url))
        try:
            _activity(page)
            rows = page.locator(f"{PANEL} .tl button.ev")
            rows.nth(0).click()
            expect(page.locator(f"{PANEL} .rd .at-msg .at-text").first).to_contain_text("Documented the flow.")
            turns = [url for url in asked if "/activity/" in url]
            assert turns and all(f"/api/archive/{name}/activity/" in url for url in turns), turns
            assert not [url for url in asked if f"/api/run/{name}/" in url]
        finally:
            page.close()


def test_a_reading_state_shows_while_an_archived_turn_is_read_and_clears_when_it_appears(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived_activity(tmp_path, "arch-reading") as name:
        page = _opened(live, name)
        held = []
        page.route(TURN_API, lambda route: held.append(route))
        try:
            _activity(page)
            reading = page.locator(f"{PANEL} .rd [role=status]")
            expect(reading).to_have_text("Reading this turn from the archive…")
            while not held:
                page.wait_for_timeout(50)
            for route in held:
                route.continue_()
            expect(reading).to_have_count(0)
            expect(page.locator(f"{PANEL} .rd .at-msg").first).to_be_visible()
        finally:
            page.close()


def test_an_unreadable_archived_turn_says_so_keeps_the_timeline_and_a_retry_shows_the_turn(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived_activity(tmp_path, "arch-retry") as name:
        page = _opened(live, name)
        answers = {"fail": True}
        page.route(TURN_API, lambda route: route.fulfill(status=503, body="no") if answers["fail"] else route.continue_())
        try:
            _activity(page)
            alert = page.locator(f"{PANEL} .rd [role=alert]")
            expect(alert).to_contain_text("This turn could not be read")
            expect(alert).to_contain_text("The rest of the run is still here.")
            assert page.locator(f"{PANEL} .tl button.ev").count() >= 2
            answers["fail"] = False
            page.locator(f"{PANEL} .retry-turn").click()
            expect(page.locator(f"{PANEL} .rd .at-msg .at-text").first).to_be_visible()
            expect(alert).to_have_count(0)
        finally:
            page.close()


def test_raw_of_an_archived_run_lists_newest_first_counts_what_it_hides_and_loads_older_on_request(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        page.locator(f'{PANEL} .feedbar [data-filter="raw"]').click()
        page.wait_for_selector(LINES, timeout=10000)
        expect(page.locator(LINES)).to_have_count(200)
        times = [page.locator(LINES).nth(number).locator(".lt-ts").inner_text() for number in range(200)]
        assert times == sorted(times, reverse=True)
        note = page.locator(f"{PANEL} .rawnote").inner_text()
        assert "newest first" in note and "3 metric samples hidden" in note, note
        older = page.locator(f"{PANEL} .load-older")
        older.scroll_into_view_if_needed()
        older.click()
        expect(page.locator(LINES)).not_to_have_count(200)
        assert page.locator(LINES).count() > 200

    _drive(tmp_path, "arch-raw", check, logs=260, samples=3)


def test_metric_samples_of_an_archived_run_stay_hidden_until_the_control_asks_for_them(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        page.locator(f'{PANEL} .feedbar [data-filter="raw"]').click()
        page.wait_for_selector(LINES, timeout=10000)
        metrics = page.locator(f'{PANEL} .feedbar [data-filter="metrics"]')
        expect(metrics).to_have_attribute("aria-pressed", "false")
        assert "METRIC" not in page.locator(f"{LINES} .lt-lvl").all_inner_texts()
        before = page.locator(LINES).count()
        metrics.click()
        expect(page.locator(LINES)).to_have_count(before + 3)
        assert page.locator(f"{LINES} .lt-lvl").all_inner_texts().count("METRIC") == 3

    _drive(tmp_path, "arch-metrics", check, samples=3)


def test_search_covers_the_rows_and_the_transcripts_of_an_archived_run(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        box = page.locator(f"{PANEL} input[type=search], {PANEL} .feedbar input")
        box.first.fill("free port")
        expect(page.locator(f"{PANEL} .tl button.ev")).to_have_count(1)
        expect(page.locator(f"{PANEL} .tl button.ev").first).to_contain_text("qa-story")
        box.first.fill(FAILED)
        expect(page.locator(f"{PANEL} .tl button.ev").first).to_contain_text(FAILED)

    _drive(tmp_path, "arch-search", check)


def test_an_archive_whose_files_are_gone_says_activity_cannot_be_read_and_the_overview_keeps_the_summary(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived_activity(tmp_path, "arch-gone") as name:
        _telemetry(name).unlink()
        page = _archive_page(live, name)
        try:
            _open_archive(page, name)
            page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)
            _activity(page)
            gone = page.locator(f"{PANEL} .side-state")
            expect(gone).to_contain_text("Activity cannot be read")
            expect(gone).to_contain_text("The Overview still shows the run's stored summary.")
            assert page.locator(f"{PANEL} .tl").count() == 0
            page.locator(f"{DETAIL}").get_by_role("tab", name="Overview").click()
            expect(page.locator(f"{DETAIL} #detail-attention-tile")).to_be_visible()
        finally:
            page.close()


def test_an_archived_transcript_goes_through_the_sanitizer(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _archived_activity(tmp_path, "arch-xss", hostile=True) as name:
        page = _opened(live, name)
        requested: list[str] = []
        page.on("request", lambda request: requested.append(request.url))
        try:
            _activity(page)
            page.locator(f"{PANEL} .tl button.ev").nth(1).click()
            expect(page.locator(f"{PANEL} .rd .at-msg .at-text").first).to_contain_text("remote logo")
            page.wait_for_timeout(300)
            assert page.evaluate("window.__pwned") is None
            assert page.locator(f"{PANEL} .rd img, {PANEL} .rd script").count() == 0
            assert not [url for url in requested if "pixel.png" in url]
        finally:
            page.close()


def test_the_archived_activity_surface_has_no_axe_violations_with_the_timeline_a_turn_and_raw_open(tmp_path):
    def check(page, name):
        page.add_script_tag(path=str(AXE))
        page.locator(f"{PANEL} .tl button.ev").nth(0).click()
        page.wait_for_selector(f"{PANEL} .rd .at-msg", timeout=10000)
        assert _scan(page) == []
        page.locator(f'{PANEL} .feedbar [data-filter="raw"]').click()
        page.wait_for_selector(LINES, timeout=10000)
        assert _scan(page) == []

    _drive(tmp_path, "arch-axe", check)


def test_a_long_run_id_keeps_the_archived_timeline_and_the_pane_inside_the_detail(tmp_path):
    def check(page, name):
        page.locator(f"{PANEL} .tl button.ev").nth(0).click()
        page.wait_for_selector(f"{PANEL} .rd .at-msg", timeout=10000)
        box = page.locator(DETAIL).bounding_box()
        for part in (f"{PANEL} .tl", f"{PANEL} .rd", f"{PANEL} .feedbar"):
            inner = page.locator(part).first.bounding_box()
            assert inner is not None and inner["x"] + inner["width"] <= box["x"] + box["width"] + 1, part
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")

    _drive(tmp_path, LONG_RUN, check)
