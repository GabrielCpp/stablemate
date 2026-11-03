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
    _scan,
    teardown_module,  # noqa: F401
)
from test_activity_groups import _pass
from test_history import refresh, seed
from test_history_dynamic import _clear, _failing_until_cleared, _history, _history_page, _open_history, _row
from test_run_clock import span

from groom import store

ASKED = "Should a locked account answer 401 or 423?"
DETAIL = "#history-detail"
AXE = Path(__file__).resolve().parent / "vendor" / "axe.min.js"


def _rich(run: str, base: float, terminal: str = "terminal") -> None:
    spans = [span("r1", "t1", "", "coder", "run:coder", base, 5000, {"workhorse.terminal": terminal}, 1)]
    spans += _pass("a", "qa", base + 10, "sign-in", [("lint", 5, "UNSET"), ("test", 7, "ERROR")], turn=(100, 2.0))
    waited = {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator", "workhorse.wait_outcome": "completed", "workhorse.gate_path": "gates/qa-story.md", "workhorse.gate_question": ASKED}
    spans.append(span("g1", "t1", "sa", "resolve", "wait:operator", base + 50, 30, waited, 1))
    for one in spans:
        one["run_id"] = run
    store.insert_spans(spans)


@contextmanager
def _ended(**plain: dict) -> Iterator[float]:
    now = time.time()
    _clear()
    _rich("hist-a", now - 3 * 3600)
    for run, fields in plain.items():
        seed(run.replace("_", "-"), now - 2 * 3600, **fields)
    refresh(now)
    try:
        yield now
    finally:
        _clear()


def _opened(live, run: str = "hist-a", handler=None):
    page = _open_history(live, handler)
    page.wait_for_selector("#history table.ht", timeout=10000)
    page.locator("#history tr.hrow", has_text=run).first.click()
    return page


def _ready(page) -> None:
    page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)


def test_selecting_a_row_narrows_the_list_opens_the_detail_beside_it_and_marks_the_row_selected():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended(hist_b={}):
        page = _opened(live)
        try:
            _ready(page)
            table = page.locator("#history table.ht").count()
            rows = page.locator("#history .row").count()
            marked = page.locator("#history .row.selected").evaluate_all("(rows) => rows.map((r) => r.dataset.run)")
            current = page.locator("#history .row.selected").get_attribute("aria-current")
            columns = page.evaluate("getComputedStyle(document.getElementById('history-pane')).gridTemplateColumns")
            beside = page.evaluate("(() => { const a = document.getElementById('history').getBoundingClientRect(); const b = document.querySelector('#history-detail').getBoundingClientRect(); return b.left >= a.right && b.width > a.width; })()")
        finally:
            page.close()
    assert table == 0 and rows == 2
    assert marked == ["hist-a"] and current == "true"
    assert columns.split(" ")[0] == "340px"
    assert beside


def test_a_narrowed_row_shows_cost_with_priced_count_active_time_end_time_and_ending():
    live = _live()
    assert live is not None, _UNAVAILABLE
    rows = [_row("hist-a", 1, cost_usd=20.0, priced_turns=1, turns=2, active_s=4500.0, ending="failed"), _row("hist-b", 2)]
    with _history(*rows):
        page = _opened(live)
        try:
            page.wait_for_selector("#history .row")
            first = page.locator("#history .row").first.locator(".line3").inner_text()
            kept = page.locator("#history .row").first.locator(".repo-branch").inner_text()
        finally:
            page.close()
    assert re.fullmatch(r"\$20\.00\s+1/2\s+1h 15m\s+[A-Z][a-z]{2} \d{1,2} \d\d:\d\d\s+FAILED", first.replace("\n", " "))
    assert kept == "acme@main"


def test_the_close_control_returns_to_the_full_table_and_the_detail_closes():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(_row("hist-a", 1), _row("hist-b", 2)):
        page = _opened(live)
        try:
            page.wait_for_selector(f"{DETAIL} .dtabs")
            page.get_by_role("button", name="Close run").click()
            page.wait_for_selector("#history table.ht")
            shown = page.locator(DETAIL).is_visible()
            rows = page.locator("#history .row").count()
            focused = page.evaluate("document.activeElement.dataset.run")
            title = page.locator("#history-title").inner_text()
            hidden = page.locator("#history-close").is_hidden()
        finally:
            page.close()
    assert not shown and rows == 0
    assert focused == "hist-a"
    assert title.lower().startswith("history: runs that ended") and hidden


def test_an_ended_run_has_overview_and_activity_tabs_and_no_files_or_diff_tab_even_when_it_ran_in_a_container():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            tabs = page.locator(f"{DETAIL} [role=tab]").evaluate_all("(tabs) => tabs.map((t) => t.id)")
            sidecar = page.locator(f"{DETAIL} #run-sidecar-chip").count()
        finally:
            page.close()
    assert tabs == ["tab-overview", "tab-activity"]
    assert sidecar == 0


def test_the_run_head_says_ended_with_its_end_time_and_its_ending_in_words_and_no_running_chip():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            page.wait_for_selector(f"{DETAIL} .detail-head")
            chips = page.locator(f"{DETAIL} .detail-head .pulse").all_inner_texts()
            line = page.locator(f"{DETAIL} .doing-line").inner_text()
            head = page.locator(f"{DETAIL} .detail-head").inner_text()
            dot = page.locator(f"{DETAIL} .detail-head .dot").get_attribute("class")
        finally:
            page.close()
    assert [chip.lower() for chip in chips] == ["ended"]
    assert re.fullmatch(r"ended [A-Z][a-z]{2} \d{1,2} \d\d:\d\d · success", line)
    assert "running" not in head.lower() and "pid" not in head
    assert "finished" in dot


def test_the_overview_shows_the_same_sections_as_a_live_run_with_no_burn_rate_and_no_current_turn_strip():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            tiles = page.locator(f"{DETAIL} .kpis .tile, {DETAIL} .kpis > *").all_inner_texts()
            sections = [page.locator(f"{DETAIL} {sel}").count() for sel in ("#detail-wall-clock", "#detail-facts", "#detail-sessions", "#detail-cost-tile", "#detail-attention-tile")]
            text = page.locator(f"{DETAIL} .ov").inner_text()
            strip = page.locator(f"{DETAIL} .now-strip, {DETAIL} #detail-now").count()
            facts = page.locator(f"{DETAIL} #detail-facts dt").all_inner_texts()
        finally:
            page.close()
    assert all(count >= 1 for count in sections)
    assert "per active hour" not in text and "as of the last finished turn" not in text and "Cost so far" not in text
    assert strip == 0
    assert any("turns priced" in tile for tile in tiles)
    assert facts[:3] == ["Ending", "Started", "Ended"]


def test_the_sessions_table_says_how_each_session_stopped():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            how = page.locator(f"{DETAIL} #detail-sessions td.how").all_inner_texts()
        finally:
            page.close()
    assert how == ["finished"]


def test_the_activity_tab_opens_the_timeline_with_finished_items_folded_no_follow_state_and_no_live_pill():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .tl button", timeout=15000)
            items = page.locator(f"{DETAIL} .tl [aria-expanded]").evaluate_all("(rows) => rows.map((r) => r.getAttribute('aria-expanded'))")
            follow = page.locator(f"{DETAIL} [data-follow], {DETAIL} .follow, {DETAIL} .newpill, {DETAIL} .livepill").count()
            body = page.locator(DETAIL).inner_text()
        finally:
            page.close()
    assert items and "true" not in items[:1]
    assert follow == 0
    assert "Following" not in body and "Paused" not in body and "LIVE" not in body


def test_an_answered_gate_reads_in_activity_only_and_the_detail_has_no_answer_box():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            before = page.locator(f"{DETAIL} textarea, {DETAIL} .gate-strip, {DETAIL} form").count()
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .tl button", timeout=15000)
            closed = page.locator(f"{DETAIL} .tl button[aria-expanded=false]")
            for _ in range(30):
                if not closed.count():
                    break
                closed.first.click()
            gate = page.locator(f'{DETAIL} .tl button[data-entry^="gate:"]').count()
            after = page.locator(f"{DETAIL} textarea, {DETAIL} .gate-strip, {DETAIL} form").count()
            send = page.get_by_role("button", name="Send answer").count()
        finally:
            page.close()
    assert before == 0 and after == 0 and send == 0
    assert gate == 1


def test_the_activity_badge_the_attention_tile_and_the_list_problem_column_show_one_number():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _history_page(live)
        try:
            column = int(page.locator("#history tr.hrow", has_text="hist-a").locator("td").nth(10).inner_text())
            page.locator("#history tr.hrow", has_text="hist-a").click()
            _ready(page)
            attention = int(re.findall(r"(\d+) problem", page.locator(f"{DETAIL} #detail-attention-tile").inner_text())[0])
            badge = int(re.findall(r"(\d+)", page.locator(f"{DETAIL} #tab-activity").inner_text())[0])
        finally:
            page.close()
    assert column >= 1
    assert column == attention == badge


def test_a_backend_with_no_cost_shows_the_labelled_estimate_in_the_cost_tile_and_an_output_column_in_the_breakdown():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended(hist_b={"costs": (None,)}):
        page = _opened(live, "hist-b")
        try:
            _ready(page)
            tile = page.locator(f"{DETAIL} #detail-cost-tile").inner_text()
            headers = page.locator(f"{DETAIL} #detail-breakdown th, {DETAIL} .ov table th").all_inner_texts()
        finally:
            page.close()
    assert re.fullmatch(r"COST\s+est \$\d+\.\d\d\s+estimate: this backend reports no cost", tile.strip().replace("\n", " "), re.I)
    assert any(header.lower() == "output" for header in headers)
    assert not any(header == "Cost" for header in headers)


def test_while_a_run_is_read_the_detail_shows_a_reading_state_that_clears_when_the_overview_appears():
    live = _live()
    assert live is not None, _UNAVAILABLE
    held: list = []
    with _ended():
        page = _open_history(live)
        page.route("**/overview", lambda route: held.append(route))
        try:
            page.wait_for_selector("#history table.ht", timeout=10000)
            page.locator("#history tr.hrow", has_text="hist-a").click()
            page.wait_for_selector(f"{DETAIL} .loading", timeout=10000)
            text = page.locator(f"{DETAIL} .loading").inner_text()
            role = page.locator(f"{DETAIL} .loading").get_attribute("role")
            held[0].continue_()
            _ready(page)
            remaining = page.locator(f"{DETAIL} .loading").count()
        finally:
            page.close()
    assert text.strip() == "Reading this run…"
    assert role == "status"
    assert remaining == 0


def test_a_failed_read_says_the_run_figures_could_not_be_read_keeps_the_list_and_a_retry_shows_the_overview():
    live = _live()
    assert live is not None, _UNAVAILABLE
    answers, answer = _failing_until_cleared()

    with _ended():
        page = _open_history(live)
        page.route("**/overview", answer)
        try:
            page.wait_for_selector("#history table.ht", timeout=10000)
            page.locator("#history tr.hrow", has_text="hist-a").click()
            page.wait_for_selector(f"{DETAIL} .retry-overview", timeout=10000)
            text = page.locator(f"{DETAIL} [role=alert]").inner_text()
            rows = page.locator("#history .row").count()
            answers["fail"] = False
            page.get_by_role("button", name="Retry now").click()
            _ready(page)
            rows_after = page.locator("#history .row").count()
        finally:
            page.close()
    assert "This run's figures could not be read" in text
    assert "The list still works." in text
    assert rows == rows_after == 1


def test_j_and_k_open_the_next_and_previous_run_in_history_and_move_the_timeline_while_activity_shows():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended(hist_b={}):
        page = _opened(live, "hist-a")
        try:
            _ready(page)
            page.locator("body").click(position={"x": 700, "y": 880})
            page.keyboard.press("j")
            page.wait_for_selector(f"{DETAIL} .ov")
            after_j = page.locator("#history .row.selected").get_attribute("data-run")
            page.keyboard.press("k")
            page.wait_for_function("document.querySelector('#history .row.selected').dataset.run === 'hist-a'")
            after_k = page.locator("#history .row.selected").get_attribute("data-run")
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .tl button", timeout=15000)
            closed = page.locator(f"{DETAIL} .tl button[aria-expanded=false]")
            for _ in range(30):
                if not closed.count():
                    break
                closed.first.click()
            page.locator(f"{DETAIL} .tl button").first.focus()
            before = page.locator(f"{DETAIL} .tl button[aria-current=true]").evaluate_all("(rows) => rows.map((r) => r.dataset.entry || r.dataset.slug)")
            page.keyboard.press("k")
            page.wait_for_timeout(300)
            moved = page.locator(f"{DETAIL} .tl button[aria-current=true]").evaluate_all("(rows) => rows.map((r) => r.dataset.entry || r.dataset.slug)")
            kept = page.locator("#history .row.selected").get_attribute("data-run")
        finally:
            page.close()
    assert after_j != "hist-a" and after_k == "hist-a"
    assert kept == "hist-a"
    assert moved != before


def test_every_new_control_has_a_role_an_accessible_name_and_keyboard_operation():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(_row("hist-a", 1), _row("hist-b", 2)):
        page = _open_history(live)
        try:
            page.wait_for_selector("#history table.ht", timeout=10000)
            page.locator("#history tr.hrow", has_text="hist-b").focus()
            page.keyboard.press("Enter")
            page.wait_for_selector("#history .row.selected")
            opened = page.locator("#history .row.selected").get_attribute("data-run")
            focused = page.evaluate("document.activeElement.dataset.run")
            roles = page.get_by_role("button", name="Close run").count()
            page.get_by_role("button", name="Close run").focus()
            page.keyboard.press("Enter")
            page.wait_for_selector("#history table.ht")
            back = page.evaluate("document.activeElement.dataset.run")
            tabs = page.locator("#history tr.hrow", has_text="hist-a")
            tabs.focus()
            page.keyboard.press(" ")
            page.wait_for_selector("#history .row.selected")
            by_space = page.locator("#history .row.selected").get_attribute("data-run")
            listed = page.get_by_role("list", name="Runs that ended, newest first").count()
            current = page.get_by_role("button").filter(has_text="hist-b").count()
        finally:
            page.close()
    assert opened == "hist-b" and focused == "hist-b"
    assert roles == 1 and back == "hist-b"
    assert by_space == "hist-a"
    assert listed == 1 and current == 1


def test_the_opened_history_has_no_accessibility_violations():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended(hist_b={"costs": (None,)}):
        page = _opened(live, "hist-a")
        try:
            _ready(page)
            page.add_script_tag(path=str(AXE))
            overview = _scan(page)
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .tl button", timeout=15000)
            activity = _scan(page)
        finally:
            page.close()
    assert not overview, json.dumps(overview, indent=1)
    assert not activity, json.dumps(activity, indent=1)


LONG_RUN = "hist-a-" + "r" * 53
LONG_REPO = "r" * 45


def _long_names():
    return _history(_row(LONG_RUN, 1, repo=LONG_REPO), _row("hist-b", 2))


def test_a_long_run_id_and_repo_label_stay_inside_the_narrowed_list_and_the_head_wraps_the_whole_id():
    live = _live()
    assert live is not None, _UNAVAILABLE
    run = LONG_RUN
    with _long_names():
        page = _opened(live, run)
        try:
            page.wait_for_selector(f"{DETAIL} .detail-head")
            row = page.locator("#history .row").first
            box = row.evaluate("(el) => { const r = el.getBoundingClientRect(); return [r.left, r.right, el.scrollWidth, el.clientWidth]; }")
            inside = row.locator(".line3 > *").evaluate_all("(els, right) => els.every((e) => e.getBoundingClientRect().right <= right + 1)", box[1])
            id_title = row.locator(".wid").get_attribute("title")
            before = page.locator("#history").evaluate("(el) => el.getBoundingClientRect().width")
            page.locator("#history .row", has_text="hist-b").click()
            page.wait_for_selector(f"{DETAIL} .detail-head")
            after = page.locator("#history").evaluate("(el) => el.getBoundingClientRect().width")
            head_id = page.locator(f"{DETAIL} .run-id").inner_text()
            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        finally:
            page.close()
    assert box[2] <= box[3] and inside
    assert id_title == run
    assert before == after
    assert head_id == "hist-b"
    assert not overflow


def test_runs_and_history_render_the_one_detail_component():
    source = (Path(__file__).resolve().parent.parent / "groom" / "assets" / "dashboard.js").read_text()
    assert source.count("function DetailBody(") == 1
    assert 'html`<${Detail} ended=${true} />`' in source
    assert '["detail", Detail]' in source
    assert '["history-detail", HistoryDetail]' in source


def test_a_workflow_chip_stays_on_one_line_at_its_natural_width_in_the_narrowed_list():
    live = _live()
    assert live is not None, _UNAVAILABLE
    rows = (
        _row("hist-a", 1, workflow="review-debt", repo="r" * 45),
        _row("hist-b", 2, workflow="okf-book", repo="tmpzl03r98h-worktree-agent"),
        _row("hist-c", 3),
    )
    with _history(*rows):
        page = _opened(live, "hist-c")
        try:
            page.wait_for_selector(f"{DETAIL} .detail-head")
            heights = page.locator("#history .row .badge").evaluate_all("(els) => els.map((e) => [Math.round(e.getBoundingClientRect().height), e.scrollWidth <= e.clientWidth])")
        finally:
            page.close()
    assert len({height for height, _ in heights}) == 1
    assert all(fits for _, fits in heights)


def test_the_overview_uses_the_mock_wording_for_the_heading_the_clock_and_the_breakdown():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            text = page.locator(DETAIL).inner_text()
            tables = page.get_by_role("table", name="Time and cost per flow").count()
            clock = page.locator(f"{DETAIL} #detail-wall-clock").inner_text()
        finally:
            page.close()
    assert re.search(r"where the time and money went", text, re.I)
    assert not re.search(r"time and cost per", text, re.I)
    assert "from first span to last span" in clock and re.search(r"\bInfra\b", clock) and "Infrastructure" not in clock
    assert tables == 1


def test_the_activity_filter_bar_labels_the_problems_pill_only_and_the_others_also_show():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .feedbar", timeout=15000)
            labels = page.locator(f"{DETAIL} .feedbar .flabel").all_inner_texts()
            order = page.locator(f"{DETAIL} .feedbar .flabel, {DETAIL} .feedbar .fchip.prob").evaluate_all("(els) => els.map((e) => e.className.includes('prob') ? 'pill' : e.textContent)")
        finally:
            page.close()
    assert [label.lower() for label in labels] == ["only", "also show"]
    assert order[:2] == ["Only", "pill"]


def test_facts_and_sessions_write_a_time_without_a_comma_and_the_copy_button_keeps_a_gap():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended():
        page = _opened(live)
        try:
            _ready(page)
            facts = page.locator(f"{DETAIL} #detail-facts dd").first.evaluate("(dd) => { const v = dd.querySelector('.fv').getBoundingClientRect(); const b = dd.querySelector('.copy').getBoundingClientRect(); return b.left - v.right; }")
            text = page.locator(f"{DETAIL} #detail-facts").inner_text()
            cell = page.locator(f"{DETAIL} table tbody tr").last.inner_text()
            started = re.findall(r"[A-Z][a-z]{2} \d{1,2},? \d\d:\d\d", text + cell)
        finally:
            page.close()
    assert facts >= 5
    assert started and all("," not in one for one in started)


def test_the_node_name_in_the_turn_head_stays_on_one_line_and_the_work_item_name_wraps():
    live = _live()
    assert live is not None, _UNAVAILABLE
    long = "create-project-s-single-insert-select-into-project-container-with-a-very-long-name"
    now = time.time()
    _clear()
    spans = [span("r1", "t1", "", "coder", "run:coder", now - 7200, 5000, {"workhorse.terminal": "terminal"}, 1)]
    spans += _pass("a", "document-story", now - 7190, long, [("lint", 5, "UNSET")], turn=(100, 2.0))
    for one in spans:
        one["run_id"] = "hist-a"
    store.insert_spans(spans)
    refresh(now)
    try:
        page = _opened(live)
        try:
            _ready(page)
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .tl button", timeout=15000)
            page.wait_for_selector(f"{DETAIL} .rd-head .rd-node", timeout=15000)
            node = page.locator(f"{DETAIL} .rd-head .rd-node").first.evaluate("(el) => el.getClientRects().length + ':' + Math.round(el.getBoundingClientRect().height)")
            line = page.locator(f"{DETAIL} .rd-head .l1").first.evaluate("(el) => parseFloat(getComputedStyle(el).lineHeight) || 16")
        finally:
            page.close()
    finally:
        _clear()
    count, height = node.split(":")
    assert count == "1" and int(height) < line * 1.6
