"""Steps, Info logs and Raw in the Activity tab, and the facts the old feed carried, measured on the page the operator gets."""
from __future__ import annotations

import re
import time
from pathlib import Path

from test_activity_step_gate_dynamic import _CURRENT, _insert_logs, _stepped, _telemetry
from test_activity_tab_dynamic import _open_activity, _pick
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)

from groom import state, store

CHIP = "#detail-panel .feedbar .fchip"
LINES = "#detail-panel .raw .log-line"


def _chip(page, name: str):
    return page.locator(f'{CHIP}[data-filter="{name}"]')


def _number(chip) -> int:
    return int(chip.locator("b").inner_text().replace(",", ""))


def _drive(tmp_path: Path, run: str, check, *, tab: bool = True, **given) -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped(run, tmp_path, **given) as name:
        page = _open(live)
        try:
            _pick(page, name)
            if tab:
                _open_activity(page)
            check(page, name)
        finally:
            page.close()


def _open_items(page) -> None:
    groups = page.locator("#detail-panel .tl button.tl-group[aria-expanded=false], #detail-panel .tl button.tl-flow[aria-expanded=false]")
    while groups.count():
        groups.first.click()


def _raw(page) -> None:
    _chip(page, "raw").click()
    page.wait_for_selector(LINES, timeout=10000)


def _flood(count: int) -> None:
    now = time.time() - 3000
    store.insert_logs([
        {"run_id": _CURRENT[0], "node": "flood", "severity": "INFO", "body": f"line {number}", "ts": now + number * 0.01}
        for number in range(count)
    ])


def test_the_steps_control_opens_every_fold_shows_a_count_and_closes_them_again(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        _open_items(page)
        steps = _chip(page, "steps")
        expect(steps).to_have_attribute("aria-pressed", "false")
        assert _number(steps) > 0
        folds = page.locator("#detail-panel .tl button.steps[aria-expanded=false]")
        before = folds.count()
        assert before > 0
        steps.click()
        expect(steps).to_have_attribute("aria-pressed", "true")
        expect(folds).to_have_count(0)
        steps.click()
        expect(steps).to_have_attribute("aria-pressed", "false")
        expect(folds).to_have_count(before)

    _drive(tmp_path, "raw-steps", check)


def test_the_info_logs_control_adds_log_rows_with_a_count_and_removes_them_again(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        logs = _chip(page, "logs")
        expect(logs).to_have_attribute("aria-pressed", "false")
        wanted = _number(logs)
        assert wanted == 4
        _open_items(page)
        _chip(page, "steps").click()
        expect(page.locator('#detail-panel .tl button[data-entry^="log:"]')).to_have_count(0)
        logs.click()
        expect(logs).to_have_attribute("aria-pressed", "true")
        expect(page.locator('#detail-panel .tl button[data-entry^="log:"]')).to_have_count(wanted)
        logs.click()
        expect(logs).to_have_attribute("aria-pressed", "false")
        expect(page.locator('#detail-panel .tl button[data-entry^="log:"]')).to_have_count(0)

    _drive(tmp_path, "raw-logs", check)


def test_an_info_log_row_does_not_split_a_fold_and_reads_in_the_pane(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        _open_items(page)
        _chip(page, "steps").click()
        _chip(page, "logs").click()
        row = page.locator('#detail-panel .tl button[data-entry^="log:"]').first
        row.click()
        expect(page.locator("#detail-panel .rd")).to_contain_text("INFO")
        assert page.locator("#detail-panel .tl button.ev[aria-expanded]").count() > 0

    _drive(tmp_path, "raw-logfold", check)


def test_raw_lists_every_record_newest_first_with_time_kind_node_and_text(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        _raw(page)
        lines = page.locator(LINES)
        first = lines.first
        for part in (".lt-ts", ".lt-lvl", ".lt-node", ".lt-body"):
            assert first.locator(part).inner_text().strip()
        kinds = {lines.nth(number).locator(".lt-lvl").inner_text() for number in range(lines.count())}
        assert {"SPAN", "INFO", "ERROR"} <= kinds
        assert "METRIC" not in kinds
        times = [lines.nth(number).locator(".lt-ts").inner_text() for number in range(lines.count())]
        assert times == sorted(times, reverse=True)
        expect(page.locator("#detail-panel .rawnote")).to_contain_text("newest first")
        expect(page.locator("#detail-panel .tl")).to_have_count(0)
        expect(page.locator("#detail-panel .rd")).to_have_count(0)

    _drive(tmp_path, "raw-list", check)


def test_a_span_record_names_its_duration_and_a_failed_one_says_failed(tmp_path):
    def check(page, name):
        _raw(page)
        text = page.locator(LINES).all_inner_texts()
        assert any(re.search(r"ensure_stack\nfailed, 4\.0s", line) for line in text)
        assert any(re.search(r"run_gate\nfailed, 1m 02s", line) for line in text)

    _drive(tmp_path, "raw-span", check)


def test_raw_hides_metric_samples_until_the_control_asks_and_shows_how_many(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        _raw(page)
        metrics = _chip(page, "metrics")
        expect(metrics).to_have_attribute("aria-pressed", "false")
        assert _number(metrics) == 3
        before = page.locator(LINES).count()
        metrics.click()
        expect(metrics).to_have_attribute("aria-pressed", "true")
        expect(page.locator(LINES)).to_have_count(before + 3)
        kinds = page.locator(f"{LINES} .lt-lvl").all_inner_texts()
        assert kinds.count("METRIC") == 3
        metrics.click()
        expect(page.locator(LINES)).to_have_count(before)

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-metrics", tmp_path) as name:
        store.insert_metrics([
            {"run_id": name, "name": "workhorse.queue.depth", "ts": 1_700_000_000 + number, "value": float(number), "attrs": {"node": "lint"}}
            for number in range(3)
        ])
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            check(page, name)
        finally:
            page.close()


def test_raw_says_how_many_records_the_run_has_and_how_many_are_shown(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        _raw(page)
        note = page.locator("#detail-panel .rawnote")
        expect(note).to_contain_text("This run has")
        expect(note).to_contain_text("Showing the newest 200")
        found = re.search(r"has ([\d,]+) records", note.inner_text())
        assert found is not None
        assert int(found.group(1).replace(",", "")) > 450

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-count", tmp_path) as name:
        _flood(450)
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            check(page, name)
        finally:
            page.close()


def test_load_older_pages_past_the_first_page_keeps_the_place_and_the_last_page_removes_the_control(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-older", tmp_path) as name:
        _flood(450)
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            _raw(page)
            older = page.locator("#detail-panel .load-older")
            expect(page.locator(LINES)).to_have_count(200)
            page.locator("#detail-panel .raw").evaluate("(el) => { el.scrollTop = 600 }")
            kept = page.locator("#detail-panel .raw").evaluate("(el) => el.scrollTop")
            tenth = page.locator(LINES).nth(9).inner_text()
            older.scroll_into_view_if_needed()
            older.click()
            expect(page.locator(LINES)).to_have_count(400)
            assert page.locator(LINES).nth(9).inner_text() == tenth
            after = page.locator("#detail-panel .raw").evaluate("(el) => el.scrollTop")
            assert after >= min(kept, 600) - 5
            older.scroll_into_view_if_needed()
            older.click()
            expect(older).to_have_count(0)
            expect(page.locator("#detail-panel .rawnote")).to_contain_text("Showing all of them")
        finally:
            page.close()


def test_while_following_new_records_appear_at_the_top_and_paused_holds_them(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-follow", tmp_path, running=True) as name:
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            _raw(page)
            follow = page.locator("#detail-panel .feedbar .follow")
            expect(follow).to_have_attribute("aria-pressed", "true")
            _insert_logs("prepare_fixtures", time.time(), [("INFO", "fresh while following")])
            expect(page.locator(LINES).first).to_contain_text("fresh while following", timeout=12000)
            follow.click()
            expect(follow).to_have_attribute("aria-pressed", "false")
            held = page.locator(LINES).count()
            _insert_logs("prepare_fixtures", time.time() + 1, [("INFO", "arrived while paused")])
            page.wait_for_timeout(4500)
            assert page.locator(LINES).count() == held
            assert "arrived while paused" not in " ".join(page.locator(LINES).all_inner_texts())
            follow.click()
            expect(page.locator(LINES).first).to_contain_text("arrived while paused", timeout=12000)
        finally:
            page.close()


def test_in_raw_the_bar_holds_only_follow_metric_samples_and_raw_and_j_k_e_do_nothing(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        before = page.locator("#detail-panel .tl button.ev").count()
        assert before > 0
        _raw(page)
        bar = page.locator("#detail-panel .feedbar")
        assert bar.locator("input, select").count() == 0
        names = [chip.get_attribute("data-filter") for chip in bar.locator(".fchip").all()]
        assert names == ["metrics", "raw"]
        expect(bar.locator(".follow")).to_have_count(1)
        selected = page.locator("#runs-list .row.sel, #runs-list .row[aria-selected=true]").count()
        page.locator("#detail-panel .raw").focus()
        for key in ("j", "k", "e"):
            page.keyboard.press(key)
        assert page.locator("#runs-list .row.sel, #runs-list .row[aria-selected=true]").count() == selected
        expect(page.locator(LINES).first).to_be_visible()
        expect(page.locator("#detail-panel .rawnote")).to_have_count(1)

    _drive(tmp_path, "raw-bar", check, running=True)


def test_raw_shows_a_reading_state_while_the_records_load(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-loading", tmp_path) as name:
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            held = []
            page.route("**/api/run/*/records*", lambda route: held.append(route))
            _chip(page, "raw").click()
            reading = page.locator("#detail-panel .loading")
            expect(reading).to_contain_text("Reading this run's records")
            expect(reading).to_have_attribute("aria-busy", "true")
            held[0].continue_()
            page.wait_for_selector(LINES, timeout=10000)
        finally:
            page.close()


def test_a_failed_read_says_so_keeps_the_timeline_and_a_retry_replaces_the_message(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-failed", tmp_path) as name:
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            page.route("**/api/run/*/records*", lambda route: route.fulfill(status=500, body="{}"))
            _chip(page, "raw").click()
            alert = page.locator("#detail-panel [role=alert]")
            expect(alert).to_contain_text("could not be read")
            expect(alert).to_contain_text("The timeline still works.")
            page.unroute("**/api/run/*/records*")
            page.locator("#detail-panel .retry-raw").click()
            page.wait_for_selector(LINES, timeout=10000)
            expect(page.locator("#detail-panel [role=alert]")).to_have_count(0)
            _chip(page, "raw").click()
            expect(page.locator("#detail-panel .tl button.ev").first).to_be_visible()
        finally:
            page.close()


def test_pressing_raw_again_returns_to_the_timeline_with_the_selection_as_it_was(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        _open_items(page)
        _chip(page, "steps").click()
        page.locator("#detail-panel .tl button.ev[data-entry]").first.click()
        chosen = page.locator("#detail-panel .tl button.ev[aria-current=true]").first.get_attribute("data-entry")
        assert chosen
        _raw(page)
        _chip(page, "raw").click()
        expect(_chip(page, "raw")).to_have_attribute("aria-pressed", "false")
        expect(page.locator(f'#detail-panel .tl button[data-entry="{chosen}"]')).to_be_visible()
        expect(page.locator("#detail-panel .rd")).to_be_visible()

    _drive(tmp_path, "raw-return", check)


def test_the_tabs_are_overview_activity_files_diff_and_a_stale_saved_trail_view_is_ignored(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-tabs", tmp_path) as name:
        page = _open(live)
        try:
            page.evaluate("() => { localStorage.setItem('groom.trailView', 'telemetry'); localStorage.setItem('groom.detailTab', 'details') }")
            page.reload(wait_until="load")
            page.wait_for_selector("#runs-list .row", timeout=15000)
            _pick(page, name)
            names = [re.sub(r"\s.*", "", text) for text in page.locator("#detail .dtabs [role=tab]").all_inner_texts()]
            assert names[:2] == ["Overview", "Activity"]
            assert "Details" not in names
            expect(page.get_by_role("tab", name="Overview")).to_have_attribute("aria-selected", "true")
            assert page.locator("#detail-panel .trail-views, #detail-panel .log-trail").count() == 0
        finally:
            page.close()


def test_the_overview_strip_shows_time_in_the_node_and_a_wait_shows_its_kind_and_time(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        strip = page.locator("#detail-panel .now")
        expect(strip).to_contain_text("In node")
        expect(strip).to_contain_text("15m")
        expect(strip).to_contain_text("Waiting on you")
        expect(strip).to_contain_text("12m")

    _drive(tmp_path, "raw-strip", check, tab=False, gate="open")


def test_gas_and_pid_join_the_run_facts_each_with_a_copy_button(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-facts", tmp_path, running=True) as name:
        _telemetry(name, "prepare_fixtures")
        state.RUNS[name].pid = 4242
        state.RUNS[name].gas = 7.5
        page = _open(live)
        try:
            _pick(page, name)
            facts = page.locator("#detail-facts")
            expect(facts).to_contain_text("4242")
            expect(facts).to_contain_text("7.5")
            for what in ("pid", "gas"):
                expect(facts.get_by_role("button", name=re.compile(what, re.I))).to_have_count(1)
        finally:
            page.close()


def test_the_attend_link_sits_in_the_run_head_and_opens_the_attendant_pane_on_that_session(tmp_path):
    from playwright.sync_api import expect

    from groom import attend_ledger

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("raw-attend", tmp_path) as name:
        attend_ledger.attend_start("job-raw-1", run_id=name, workflow="coder", kind="gate", reason="open gate", session_id="sess-raw-1")
        page = _open(live)
        try:
            _pick(page, name)
            link = page.locator("#detail .detail-head .attend-link")
            expect(link).to_contain_text("an attendant is on this run")
            at, head = link.bounding_box(), page.locator("#detail .detail-head").bounding_box()
            assert at is not None and head is not None
            assert at["x"] > head["x"]
            link.click()
            expect(page.locator('.act-btn[data-mode="attend"]')).to_have_attribute("aria-pressed", "true")
        finally:
            page.close()


def test_steps_info_logs_raw_and_metric_samples_are_named_pressed_and_work_from_the_keyboard(tmp_path):
    from playwright.sync_api import expect

    def check(page, name):
        for key in ("steps", "logs"):
            chip = _chip(page, key)
            assert chip.get_attribute("aria-pressed") == "false"
            assert chip.inner_text().strip()
            chip.focus()
            page.keyboard.press("Enter")
            expect(chip).to_have_attribute("aria-pressed", "true")
            page.keyboard.press("Space")
            expect(chip).to_have_attribute("aria-pressed", "false")
        raw = _chip(page, "raw")
        raw.focus()
        page.keyboard.press("Enter")
        page.wait_for_selector(LINES, timeout=10000)
        metrics = _chip(page, "metrics")
        assert metrics.inner_text().startswith("Metric samples")
        metrics.focus()
        page.keyboard.press("Space")
        expect(metrics).to_have_attribute("aria-pressed", "true")
        _chip(page, "raw").focus()
        page.keyboard.press("Enter")
        expect(_chip(page, "raw")).to_have_attribute("aria-pressed", "false")

    _drive(tmp_path, "raw-keys", check)


def test_the_raw_view_and_the_bar_have_no_accessibility_violations(tmp_path):
    def check(page, name):
        violations = _scan(page)
        assert not violations, violations
        _chip(page, "steps").click()
        _chip(page, "logs").click()
        violations = _scan(page)
        assert not violations, violations
        _raw(page)
        _chip(page, "metrics").click()
        violations = _scan(page)
        assert not violations, violations

    _drive(tmp_path, "raw-axe", check, running=True)
