from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _export,
    _live,
    _post_turn,
    _violations_in,
    teardown_module,  # noqa: F401
)
from test_history import refresh
from test_history_open_dynamic import AXE
from test_history_dynamic import _clear, _history, _row

from groom import alerts, history, state, store

RAIL = '.act-btn[data-mode="history"]'
STRIP = "#detail #ended-strip"
ROW = "#runs-list .row"
SEEN = "groom.history.seen"
FAILED = "groom.history.failed"


def _post(live, run: str, spans: list[tuple[str, str, dict]], workflow: str = "coder", repo: str = "acme") -> None:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    for key, value in {"run_id": run, "workflow": workflow, "repo": repo, "branch": "main", "workspace": str(Path(__file__).parent)}.items():
        kv = resource_spans.resource.attributes.add()
        kv.key, kv.value.string_value = key, value
    now = time.time()
    for index, (name, node, attrs) in enumerate(spans):
        span = resource_spans.scope_spans.add().spans.add()
        span.trace_id = bytes.fromhex("cd" * 16)
        span.span_id = bytes.fromhex(f"{index + 1:016x}")
        span.name = name
        span.start_time_unix_nano = int((now - 5) * 1e9)
        span.end_time_unix_nano = int(now * 1e9)
        for key, value in {"workhorse.node": node, **attrs}.items():
            kv = span.attributes.add()
            kv.key, kv.value.string_value = key, str(value)
    _export(live, request)


def _begin(live, run: str, workflow: str = "coder", repo: str = "acme") -> None:
    _post(live, run, [("agent_turn", "qa-story", {"backend": "claude"})], workflow, repo)
    now = time.time()
    alerts.ingest_metrics([{"run_id": run, "name": "workhorse.node.active", "ts": now, "value": 1.0, "attrs": {"node": "qa-story"}}], now=now)


def _end(live, run: str, terminal: str = "terminal", **attrs: str) -> None:
    _post(live, run, [("run:coder", "", {"workhorse.terminal": terminal, **attrs})])


def _summarize(run: str) -> None:
    refresh()
    assert history.stored(run) is not None


def _forget(*runs: str) -> None:
    state.evict_runs(list(runs))
    for run in runs:
        store.delete_run_telemetry(run)
        store._chunked_delete("spans", "run_id = ?", (run,))
    _clear()


@contextmanager
def _running(live, *runs: str) -> Iterator[None]:
    _clear()
    for run in runs:
        _begin(live, run)
    try:
        yield
    finally:
        _forget(*runs)


def _page(live, selected: str = "", init: str = ""):
    page = live.browser.new_page(viewport={"width": 1400, "height": 900})
    if init:
        page.add_init_script(init)
    page.goto(live.url(), wait_until="load")
    page.wait_for_selector(ROW, timeout=15000)
    if selected:
        page.locator(ROW, has_text=selected).first.click()
        page.wait_for_selector("#detail .detail-head", timeout=10000)
    return page


def _badge(page, which: str) -> tuple[bool, str, str]:
    badge = page.locator(f"#{which}-badge")
    button = page.locator(f'.act-btn[data-mode="{which}"]')
    return badge.is_visible(), badge.inner_text(), button.get_attribute("aria-label") or ""


def _stamp_old(page) -> None:
    page.evaluate(f"() => localStorage.setItem('{SEEN}', JSON.stringify(1))")
    page.reload(wait_until="load")
    page.wait_for_selector(ROW, timeout=15000)


def test_a_selected_run_that_ends_stays_open_with_a_strip_saying_it_ended_how_long_ago_and_how():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-ok"):
        page = _page(live, "end-ok")
        try:
            assert page.locator(STRIP).count() == 0
            _end(live, "end-ok")
            page.wait_for_selector(STRIP, timeout=10000)
            text = page.locator(STRIP).inner_text()
            head = page.locator("#detail .detail-head").inner_text()
            role = page.locator(STRIP).get_attribute("role")
        finally:
            page.close()
    assert text.startswith("This run ended ") and "ago: success." in text
    assert "It stays open here." in text
    assert "end-ok" in head
    assert role == "status"


def test_the_row_and_the_head_change_to_ended_with_the_strip_and_the_tabs_leave_no_files_or_diff():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-row"):
        page = _page(live, "end-row")
        try:
            _end(live, "end-row")
            page.wait_for_selector(STRIP, timeout=10000)
            row = page.locator(ROW, has_text="end-row").first
            kind = row.get_attribute("data-state")
            doing = row.locator(".doing").inner_text()
            mini = row.locator(".mini").inner_text()
            head_state = page.locator("#detail .detail-head .dot, #detail .detail-head [data-state]").first.get_attribute("class") or ""
            tabs = [name.split(" ")[0] for name in page.get_by_role("tab").all_inner_texts()]
            doing_line = page.locator("#detail .detail-head .doing-line").inner_text()
        finally:
            page.close()
    assert kind == "finished" and doing == "finished"
    assert mini.startswith("ended ") and mini.endswith(" ago")
    assert "finished" in head_state
    assert tabs == ["Overview", "Activity"]
    assert doing_line.startswith("ended ") and doing_line.endswith("success")


def _announce(run: str) -> None:
    from groom import app

    queue = next(iter(state.CLIENTS))
    asyncio.run_coroutine_threadsafe(app._write_summary(run), vars(queue)["_loop"]).result(timeout=20)


def _wait_ended(page, run: str) -> None:
    page.wait_for_selector(f'{ROW}[data-state="finished"]', timeout=10000)
    page.wait_for_selector(STRIP, timeout=10000)


def test_a_run_that_fails_while_open_shows_its_failure_banner_under_the_strip():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-bad"):
        page = _page(live, "end-bad")
        try:
            _end(live, "end-bad", "fail", **{"error.class": "WatchdogKilled", "error.kind": "fatal"})
            page.wait_for_selector(STRIP, timeout=10000)
            strip = page.locator(STRIP).inner_text()
            klass = page.locator(STRIP).get_attribute("class") or ""
            assert page.locator("#detail #detail-ending").count() == 0
            _announce("end-bad")
            page.wait_for_selector("#detail #detail-ending", timeout=10000)
            above = page.evaluate("() => document.querySelector('#ended-strip').compareDocumentPosition(document.querySelector('#detail-ending')) & Node.DOCUMENT_POSITION_FOLLOWING")
            banner = page.locator("#detail #detail-ending h2").inner_text()
        finally:
            page.close()
    assert "failed at qa-story." in strip and "fail" in klass.split()
    assert above
    assert banner == "Ended: WatchdogKilled"


_SCAN_NEW = _violations_in('{ include: [["#ended-strip"], ["#activitybar"], ["#runs-list"]] }')


def _block(live, run: str) -> None:
    now = time.time()
    attrs = {"node": "await_operator", "wait_kind": "operator", "gate_path": "gates/q.md", "gate_question": "Which one?"}
    alerts.ingest_metrics([{"run_id": run, "name": "workhorse.wait.active", "ts": now, "value": 1.0, "attrs": attrs}], now=now)
    _begin(live, run)


def _default_ending(page) -> str:
    return page.get_by_role("combobox", name="Ending").locator("option").first.inner_text()


def _history_text(page) -> list[str]:
    return page.locator("#history table.ht tbody tr, #history .row").evaluate_all("(rows) => rows.map((row) => row.dataset.run)")


def test_the_strip_links_to_the_run_in_history_and_clears_a_filter_that_would_hide_it():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-go"), _history(_row("hist-a", 1)):
        page = _page(live)
        try:
            page.click(RAIL)
            page.wait_for_selector("#history table.ht", timeout=10000)
            page.get_by_role("combobox", name="Ending").select_option(label="success")
            page.click('.act-btn[data-mode="runs"]')
            page.locator(ROW, has_text="end-go").first.click()
            _end(live, "end-go", "fail", **{"error.kind": "fatal"})
            page.wait_for_selector(STRIP, timeout=10000)
            _announce("end-go")
            page.get_by_role("link", name="Open it in History").click()
            page.wait_for_selector("#history .row.selected", timeout=10000)
            selected = page.locator("#history .row.selected").get_attribute("data-run")
            mode = page.locator(".app").get_attribute("data-mode")
            detail = page.locator("#history-detail .detail-head").inner_text()
            page.get_by_role("button", name="Close run").click()
            page.wait_for_selector("#history table.ht", timeout=10000)
            picked = page.get_by_role("combobox", name="Ending").evaluate("(el) => el.selectedOptions[0].textContent")
            first = _default_ending(page)
        finally:
            page.close()
    assert selected == "end-go" and mode == "history"
    assert picked == first
    assert "end-go" in detail


def test_the_strip_stays_until_the_operator_selects_another_run():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-st"):
        page = _page(live, "end-st")
        try:
            _end(live, "end-st")
            page.wait_for_selector(STRIP, timeout=10000)
            _post_turn(live, "ab01", usd=0.1)
            page.wait_for_timeout(1500)
            kept = page.locator(STRIP).count()
            page.locator(ROW, has_text="run-running").first.click()
            page.wait_for_selector("#detail .detail-head", timeout=10000)
            gone = page.locator(STRIP).count()
        finally:
            page.close()
    assert kept == 1 and gone == 0


def test_a_selected_runs_row_that_is_evicted_leaves_the_detail_open_and_the_list_without_a_row():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-ev"):
        page = _page(live, "end-ev")
        try:
            _end(live, "end-ev")
            page.wait_for_selector(STRIP, timeout=10000)
            state.evict_runs(["end-ev"])
            _post_turn(live, "ab02", usd=0.1)
            page.wait_for_function("(id) => ![...document.querySelectorAll('#runs-list .row')].some((row) => row.textContent.includes(id))", arg="end-ev", timeout=10000)
            strip = page.locator(STRIP).count()
            head = page.locator("#detail .detail-head").inner_text()
        finally:
            page.close()
    assert strip == 1
    assert "end-ev" in head


def test_a_run_that_fails_crashes_or_is_stopped_by_a_fatal_error_raises_the_history_badge_by_one_each():
    live = _live()
    assert live is not None, _UNAVAILABLE
    ends = {
        "bd-fail": ("fail", {"error.kind": "fatal"}),
        "bd-fatal": ("interrupted", {"error.kind": "fatal"}),
        "bd-crash": ("aborted", {}),
    }
    with _running(live, *ends):
        page = _page(live)
        try:
            for run, (terminal, attrs) in ends.items():
                _end(live, run, terminal, **attrs)
            page.wait_for_function("() => document.getElementById('history-badge').textContent === '3'", timeout=10000)
            shown = _badge(page, "history")
        finally:
            page.close()
    assert shown == (True, "3", "History, 3 runs failed since you last looked")


def _fail_one(live, page, run: str, terminal: str = "fail", **attrs: str) -> None:
    _end(live, run, terminal, **attrs)
    page.wait_for_selector(f'{ROW}[data-state="finished"]', timeout=10000)
    page.wait_for_timeout(300)


def test_opening_history_clears_the_badge_and_the_count_survives_a_reload():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "bd-one"):
        page = _page(live)
        try:
            _fail_one(live, page, "bd-one", **{"error.kind": "fatal"})
            page.reload(wait_until="load")
            page.wait_for_selector(ROW, timeout=15000)
            kept = _badge(page, "history")
            page.click(RAIL)
            page.wait_for_selector("#history table.ht, #history .empty-big", timeout=10000)
            opened = _badge(page, "history")
            page.click('.act-btn[data-mode="runs"]')
            page.reload(wait_until="load")
            page.wait_for_selector(ROW, timeout=15000)
            after = _badge(page, "history")
        finally:
            page.close()
    assert kept == (True, "1", "History, 1 run failed since you last looked")
    assert opened == (False, "", "History")
    assert after == (False, "", "History")


def test_a_success_a_stop_the_operator_asked_for_and_a_reload_raise_no_badge():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "bd-ok", "bd-stop", "bd-re"):
        page = _page(live)
        try:
            _end(live, "bd-ok")
            _end(live, "bd-stop", "interrupted", **{"error.kind": "interrupt", "error.class": "KeyboardInterrupt"})
            _end(live, "bd-re", "reload")
            page.wait_for_function("() => document.querySelectorAll('#runs-list .row[data-state=finished]').length >= 3", timeout=10000)
            page.wait_for_timeout(500)
            shown = _badge(page, "history")
        finally:
            page.close()
    assert shown == (False, "", "History")


def test_a_first_load_with_no_last_opened_time_shows_no_badge_and_sets_that_time_to_now():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "bd-old"):
        _end(live, "bd-old", "fail", **{"error.kind": "fatal"})
        before = time.time()
        page = _page(live)
        try:
            shown = _badge(page, "history")
            stamp = page.evaluate(f"() => JSON.parse(localStorage.getItem('{SEEN}'))")
        finally:
            page.close()
    assert shown == (False, "", "History")
    assert before - 2 <= stamp <= time.time() + 2


def test_a_run_that_failed_before_the_dashboard_loaded_counts_when_it_failed_after_the_last_open():
    live = _live()
    assert live is not None, _UNAVAILABLE
    old = f"if (localStorage.getItem('{SEEN}') === null) localStorage.setItem('{SEEN}', '1')"
    with _running(live, "bd-pre"):
        _end(live, "bd-pre", "fail", **{"error.kind": "fatal"})
        page = _page(live, init=old)
        try:
            shown = _badge(page, "history")
        finally:
            page.close()
    assert shown == (True, "1", "History, 1 run failed since you last looked")


def test_the_last_opened_time_lives_in_the_browser_and_the_server_is_told_nothing():
    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _page(live)
    sent: list[str] = []
    page.on("request", lambda request: sent.append(request.method + " " + request.url) if request.method != "GET" else None)
    try:
        page.click(RAIL)
        page.wait_for_selector("#history table.ht, #history .empty-big", timeout=10000)
        page.click('.act-btn[data-mode="runs"]')
        stamp = page.evaluate(f"() => localStorage.getItem('{SEEN}')")
    finally:
        page.close()
    assert stamp is not None
    assert sent == []


def test_a_run_that_becomes_blocked_raises_the_runs_badge_while_history_is_open():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "bk-one"):
        page = _page(live)
        try:
            page.click(RAIL)
            page.wait_for_selector("#history table.ht, #history .empty-big", timeout=10000)
            before = _badge(page, "runs")
            _block(live, "bk-one")
            page.wait_for_function("() => document.getElementById('runs-badge').textContent === '2'", timeout=10000)
            after = _badge(page, "runs")
        finally:
            page.close()
    assert before == (True, "1", "Runs, 1 blocked run")
    assert after == (True, "2", "Runs, 2 blocked runs")


def test_a_run_that_ends_while_history_is_open_tops_the_table_the_totals_follow_and_an_open_run_stays_open():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "end-hi"), _history(_row("hist-a", 1)):
        page = _page(live)
        try:
            page.click(RAIL)
            page.wait_for_selector("#history table.ht", timeout=10000)
            before = _totals_runs(page)
            _end(live, "end-hi", "fail", **{"error.kind": "fatal"})
            _announce("end-hi")
            page.wait_for_function("() => document.querySelector('#history tr.hrow')?.dataset.run === 'end-hi'", timeout=10000)
            order = _history_text(page)
            after = _totals_runs(page)
            page.locator("#history tr.hrow", has_text="hist-a").first.click()
            page.wait_for_selector("#history-detail .detail-head", timeout=10000)
            _end(live, "end-hi", "fail", **{"error.kind": "fatal"})
            _announce("end-hi")
            page.wait_for_timeout(800)
            open_run = page.locator("#history .row.selected").get_attribute("data-run")
            badge = _badge(page, "history")
        finally:
            page.close()
    assert order[:2] == ["end-hi", "hist-a"]
    assert after == before + 1
    assert open_run == "hist-a"
    assert badge == (False, "", "History")


def _totals_runs(page) -> int:
    return int(page.locator("#history .h-sum span").first.inner_text().split()[0])


def test_the_runs_tab_keeps_a_run_that_is_not_ending_as_it_was():
    live = _live()
    assert live is not None, _UNAVAILABLE
    page = _page(live, "run-running")
    try:
        row = page.locator(ROW, has_text="run-running").first
        klass = row.get_attribute("class") or ""
        strip = page.locator(STRIP).count()
        tabs = len(page.get_by_role("tab").all())
    finally:
        page.close()
    assert "ended" not in klass.split()
    assert strip == 0 and tabs >= 2


def test_the_strip_and_both_badges_pass_an_axe_scan_and_the_link_works_from_the_keyboard():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "ax-one"):
        page = _page(live, "ax-one")
        try:
            _end(live, "ax-one", "fail", **{"error.kind": "fatal"})
            page.wait_for_selector(STRIP, timeout=10000)
            page.wait_for_function("() => document.getElementById('history-badge').textContent === '1'", timeout=10000)
            page.add_script_tag(path=str(AXE))
            found = page.evaluate(_SCAN_NEW)
            link = page.get_by_role("link", name="Open it in History")
            link.focus()
            page.keyboard.press("Enter")
            page.wait_for_selector("#history-pane", state="visible", timeout=10000)
            mode = page.locator(".app").get_attribute("data-mode")
        finally:
            page.close()
    assert not found, json.dumps(found, indent=1)
    assert mode == "history"


def _toast(page, text: str) -> tuple[str, str]:
    page.wait_for_function("(text) => [...document.querySelectorAll('#toasts .toast')].some((t) => t.textContent.includes(text))", arg=text, timeout=10000)
    return page.evaluate(
        "(text) => { const t = [...document.querySelectorAll('#toasts .toast')].find((x) => x.textContent.includes(text)); return [t.querySelector('.t-title').textContent, t.className]; }",
        text,
    )


def test_a_successful_ending_toasts_run_ended_and_not_worker_blocked():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "ty-ok"):
        page = _page(live)
        try:
            _end(live, "ty-ok")
            title, klass = _toast(page, "ty-ok")
        finally:
            page.close()
    assert title == "run ended"
    assert "blocked" not in klass.split()


def test_a_failed_ending_toasts_run_ended_in_the_red_tone():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "ty-bad"):
        page = _page(live)
        try:
            _end(live, "ty-bad", "fail", **{"error.class": "WatchdogKilled", "error.kind": "fatal"})
            title, klass = _toast(page, "ty-bad")
        finally:
            page.close()
    assert title == "run ended"
    assert "blocked" in klass.split()


def test_a_blocked_notify_still_toasts_worker_blocked():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "ty-bk"):
        page = _page(live)
        try:
            _block(live, "ty-bk")
            title, klass = _toast(page, "waiting on gates/q.md")
        finally:
            page.close()
    assert title == "⛔ worker blocked"
    assert "blocked" in klass.split()


LONG_RUN = "coder-" + "x" * 53 + "z"
LONG_REPO = "acme-platform-" + "r" * 31
_GEOMETRY = """(id) => {
  const box = (el) => el.getBoundingClientRect();
  const row = document.querySelector('#runs-list .row[data-worker-id="' + id + '"]');
  const badge = (type) => box(document.querySelector('#runs-list .row .badge[data-type="' + type + '"]'));
  return {
    row: box(row).toJSON(), pill: box(row.querySelector('.pulse')).toJSON(),
    repo: box(row.querySelector('.repo-branch')).width, wid: box(row.querySelector('.wid')).width,
    okf: badge('okf-book').height, coder: badge('coder').height,
  };
}"""


def test_a_narrowed_row_with_long_names_keeps_its_pill_inside_and_both_names_visible():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _running(live, "nr-okf"):
        _begin(live, "nr-okf", "okf-book", "acme")
        _begin(live, LONG_RUN, "coder", LONG_REPO)
        page = _page(live, LONG_RUN[:20])
        try:
            page.wait_for_selector(f'{ROW}[data-worker-id="{LONG_RUN}"] .pulse', timeout=10000)
            page.wait_for_selector('#runs-list .row .badge[data-type="okf-book"]', timeout=10000)
            geometry = page.evaluate(_GEOMETRY, LONG_RUN)
        finally:
            page.close()
            _forget(LONG_RUN)
    row, pill = geometry["row"], geometry["pill"]
    assert row["left"] <= pill["left"] and pill["right"] <= row["right"]
    assert geometry["repo"] > 0 and geometry["wid"] > 0
    assert geometry["okf"] == geometry["coder"]
