"""The Activity timeline of a live run follows it, pauses when the operator scrolls, and returns with one action, measured on the page the operator gets."""
from __future__ import annotations

import itertools
import json
import re
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from test_a11y_dynamic import (
    _UNAVAILABLE,
    AXE,
    _live,
    _scan,
    teardown_module,  # noqa: F401
)
from test_activity_tab_dynamic import RUNNING, _open_activity, _pick, _rows, _run, _turn_attrs
from test_run_clock import span

from groom import store

WATCH_SOCKETS = """(() => {
  const Native = window.WebSocket;
  window.__sockets = [];
  window.__blocked = false;
  window.__skew = 0;
  const now = Date.now.bind(Date);
  Date.now = () => now() + window.__skew;
  window.WebSocket = class extends Native {
    constructor(url, ...rest) {
      super(window.__blocked ? "ws://127.0.0.1:1/ws" : url, ...rest);
      window.__sockets.push(this);
    }
  };
})();"""

DROP = "() => { window.__blocked = true; window.__sockets.forEach((one) => one.close()); }"
RESTORE = "() => { window.__blocked = false; window.__skew = 0; }"
LONG_LOSS = "() => { window.__skew = 70000; }"
LIST = "#detail-panel .tl"
CONTROL = "#detail-panel .feedbar .follow"
PILL = "#detail-panel .newpill button"

_IDS = itertools.count(0xF1000000)


def _open_watched(live, height: int = 640):
    page = live.browser.new_page(viewport={"width": 1400, "height": height})
    page.add_init_script(WATCH_SOCKETS)
    page.goto(live.url(), wait_until="load")
    page.wait_for_selector("#runs-list .row", timeout=15000)
    page.add_script_tag(path=str(AXE))
    return page


def _send(live, run: str, *, name: str = "agent_turn", node: str = "qa-story", usd: float | None = None, slug: str = "", attrs: dict | None = None) -> str:
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    span_id = f"{next(_IDS):016x}"
    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    for key, value in {"run_id": run, "workflow": "coder"}.items():
        kv = resource_spans.resource.attributes.add()
        kv.key, kv.value.string_value = key, value
    one = resource_spans.scope_spans.add().spans.add()
    one.trace_id = bytes.fromhex("ab" * 16)
    one.span_id = bytes.fromhex(span_id)
    one.name = name
    now = time.time()
    one.start_time_unix_nano = int((now - 5) * 1e9)
    one.end_time_unix_nano = int(now * 1e9)
    given = {"workhorse.node": node, "backend": "claude", "duration_ms": 5000, **(attrs or {})}
    if slug:
        given["workhorse.visit.slug"] = slug
    if usd is not None:
        given["total_cost_usd"] = usd
    for key, value in given.items():
        kv = one.attributes.add()
        kv.key = key
        if isinstance(value, bool) or isinstance(value, str):
            kv.value.string_value = str(value)
        elif isinstance(value, float):
            kv.value.double_value = value
        else:
            kv.value.int_value = value
    http = urllib.request.Request(live.url() + "v1/traces", data=request.SerializeToString(), headers={"Content-Type": "application/x-protobuf"})
    with urllib.request.urlopen(http, timeout=10) as reply:
        assert reply.status == 200
    return span_id


def _arrive(live, run: str, count: int) -> list[str]:
    return [_send(live, run, usd=0.5) for _ in range(count)]


def _end(live, run: str) -> None:
    _send(live, run, name="run:coder", attrs={"workhorse.terminal": "terminal"})


def _stored_turn(run: str, node: str = "qa-story") -> str:
    span_id = f"{next(_IDS):016x}"
    now = time.time()
    attrs = {"backend": "claude", "total_cost_usd": 0.75, "duration_ms": 5000}
    store.insert_spans([span(span_id, "t9", "", node, "agent_turn", now - 5, 5, attrs, 1, run)])
    return span_id


@contextmanager
def _following(tmp_path: Path, run: str, *, filler: int = 30, running: bool = False, turns: bool = False, height: int = 640, ended: bool = False) -> Iterator[tuple]:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run(run, tmp_path, running=running, turns=turns) as name:
        if filler:
            _arrive(live, name, filler)
        if ended:
            _end(live, name)
        page = _open_watched(live, height)
        try:
            _pick(page, name)
            _open_activity(page)
            yield live, page, name
        finally:
            page.close()


def _bottom_gap(page) -> float:
    return page.locator(LIST).evaluate("el => el.scrollHeight - el.clientHeight - el.scrollTop")


def _in_view(page, row) -> bool:
    return page.evaluate(
        "([list, row]) => { const a = document.querySelector(list).getBoundingClientRect(); const b = row.getBoundingClientRect(); return b.top >= a.top - 1 && b.bottom <= a.bottom + 1; }",
        [LIST, row.element_handle()],
    )


def _uncovered(page, row) -> bool:
    return page.evaluate(
        "([list, row]) => { const a = document.querySelector(list).getBoundingClientRect(); const b = row.getBoundingClientRect(); const x = b.left + 60; const y = b.top + b.height / 2; if (y < a.top || y > a.bottom) return false; const hit = document.elementFromPoint(x, y); return !!hit && row.contains(hit); }",
        [LIST, row.element_handle()],
    )


def _wheel_up(page, pixels: int = 400) -> None:
    box = page.locator(LIST).bounding_box()
    page.mouse.move(box["x"] + 40, box["y"] + 100)
    page.mouse.wheel(0, -pixels)


def _newest(page):
    return _rows(page).last


def test_a_live_runs_timeline_shows_a_control_that_says_it_is_following(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-ctl") as (_live_, page, _name):
        control = page.locator(CONTROL)
        expect(control).to_have_count(1)
        expect(control).to_have_text("Following")
        expect(control).to_have_attribute("aria-pressed", "true")
        expect(page.locator(PILL)).to_have_count(0)


def test_new_rows_appear_at_the_end_while_following_and_the_newest_stays_in_view(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-end") as (live, page, name):
        before = _rows(page).count()
        assert page.locator(LIST).evaluate("el => el.scrollHeight > el.clientHeight"), "the timeline must overflow for this test to mean anything"
        assert _bottom_gap(page) <= 4
        last = _arrive(live, name, 3)
        expect(_rows(page)).to_have_count(before + 3)
        assert _newest(page).get_attribute("data-slug") == f"unmatched-{last[-1]}"
        assert _in_view(page, _newest(page))
        assert _bottom_gap(page) <= 4
        expect(page.locator(CONTROL)).to_have_text("Following")


def test_a_running_turns_row_and_pane_show_new_messages_and_tool_calls_as_they_arrive(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-run", filler=0, running=True) as (_live_, page, name):
        live_file = tmp_path / "runs" / name / "transcripts" / "live" / f"{RUNNING}.jsonl"
        expect(page.locator(".rd .at-text")).to_have_text("Rerunning the locked account scenario.")
        row = page.locator(f'#detail-panel .tl button[data-slug="{RUNNING}"]')
        expect(row.locator(".w")).to_have_text("Rerunning the locked account scenario.")
        with live_file.open("a") as handle:
            for update in (
                {"sessionUpdate": "tool_call", "toolCallId": "c9", "title": "Bash pytest -q", "status": "in_progress", "rawInput": {"command": "pytest -q"}},
                {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "All nine scenarios pass now."}},
            ):
                handle.write(json.dumps({"sessionId": "sess-1", "update": update, "_meta": {"ts": time.time(), "node": "qa-story"}}) + "\n")
        expect(page.locator(".rd .at-tool-name")).to_have_text("Bash", timeout=10000)
        expect(page.locator(".rd .at-msg").last).to_contain_text("All nine scenarios pass now.", timeout=10000)
        expect(row.locator(".w")).to_have_text("All nine scenarios pass now.", timeout=10000)
        assert ", running," in (row.get_attribute("aria-label") or "")


def test_the_selected_row_stays_selected_while_new_rows_arrive_and_the_pane_does_not_change(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-sel", filler=3) as (live, page, name):
        before = _rows(page).count()
        older = _rows(page).nth(1)
        older.click()
        slug = older.get_attribute("data-slug")
        expect(older).to_have_attribute("aria-current", "true")
        head = page.locator(".rd .rd-head").inner_text()
        _arrive(live, name, 4)
        expect(_rows(page)).to_have_count(before + 4)
        page.wait_for_timeout(600)
        current = page.locator(f'#detail-panel .tl button[data-slug="{slug}"]')
        expect(current).to_have_attribute("aria-current", "true")
        assert page.locator("#detail-panel .tl button[aria-current=true]").count() == 1
        assert page.locator(".rd .rd-head").inner_text() == head


def test_scrolling_up_pauses_the_follow_and_the_control_says_paused(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-pause") as (_live_, page, _name):
        _wheel_up(page)
        control = page.locator(CONTROL)
        expect(control).to_have_text("Paused")
        expect(control).to_have_attribute("aria-pressed", "false")
        assert _bottom_gap(page) > 4


def test_while_paused_rows_already_in_view_stay_where_they_are(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-stay") as (live, page, name):
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        marked = _rows(page).nth(3)
        top_before = marked.bounding_box()["y"]
        scroll_before = page.locator(LIST).evaluate("el => el.scrollTop")
        count = _rows(page).count()
        _arrive(live, name, 4)
        expect(_rows(page)).to_have_count(count + 4)
        page.wait_for_timeout(600)
        assert page.locator(LIST).evaluate("el => el.scrollTop") == scroll_before
        assert abs(marked.bounding_box()["y"] - top_before) < 1
        expect(page.locator(CONTROL)).to_have_text("Paused")


def test_while_paused_a_group_that_finishes_stays_open_under_the_operators_eyes(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-hold", turns=True) as (live, page, name):
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        heads = page.locator("#detail-panel .tl button[aria-expanded=true].tl-flow, #detail-panel .tl button[aria-expanded=true].tl-group")
        opened = heads.count()
        assert opened > 0
        _end(live, name)
        expect(page.locator(".feedbar")).to_have_count(0, timeout=10000)
        page.wait_for_timeout(500)
        assert heads.count() == opened


def test_while_paused_a_pill_counts_what_has_arrived(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-pill") as (live, page, name):
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        expect(page.locator(PILL)).to_have_count(0)
        _arrive(live, name, 3)
        expect(page.locator(PILL)).to_contain_text("3 new")
        _arrive(live, name, 2)
        expect(page.locator(PILL)).to_contain_text("5 new")
        expect(page.locator(PILL)).to_contain_text("back to live")


def test_pressing_the_pill_scrolls_to_the_newest_row_clears_it_and_resumes_following(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-back") as (live, page, name):
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        last = _arrive(live, name, 3)
        expect(page.locator(PILL)).to_contain_text("3 new")
        page.locator(PILL).click()
        expect(page.locator(PILL)).to_have_count(0)
        expect(page.locator(CONTROL)).to_have_text("Following")
        assert _newest(page).get_attribute("data-slug") == f"unmatched-{last[-1]}"
        assert _in_view(page, _newest(page))
        assert _bottom_gap(page) <= 4
        _arrive(live, name, 1)
        expect(page.locator(PILL)).to_have_count(0)


def test_scrolling_back_to_the_end_resumes_following(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-end2") as (live, page, name):
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        _arrive(live, name, 2)
        expect(page.locator(PILL)).to_contain_text("2 new")
        page.locator(LIST).evaluate("el => { el.scrollTop = el.scrollHeight; }")
        expect(page.locator(CONTROL)).to_have_text("Following")
        expect(page.locator(PILL)).to_have_count(0)
        _arrive(live, name, 1)
        expect(page.locator(PILL)).to_have_count(0)
        page.wait_for_timeout(400)
        assert _bottom_gap(page) <= 4


def test_pressing_the_control_switches_between_following_and_paused(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-flip") as (live, page, name):
        control = page.locator(CONTROL)
        control.click()
        expect(control).to_have_text("Paused")
        top = page.locator(LIST).evaluate("el => el.scrollTop")
        _arrive(live, name, 2)
        expect(page.locator(PILL)).to_contain_text("2 new")
        assert page.locator(LIST).evaluate("el => el.scrollTop") == top
        control.click()
        expect(control).to_have_text("Following")
        expect(page.locator(PILL)).to_have_count(0)
        assert _bottom_gap(page) <= 4
        assert _in_view(page, _newest(page))


def test_a_lost_connection_says_the_timeline_is_not_connected(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-lost") as (_live_, page, _name):
        page.evaluate(DROP)
        control = page.locator(CONTROL)
        expect(control).to_have_text("Not connected", timeout=8000)
        expect(control).to_be_disabled()
        assert page.locator(".stat.conn").get_attribute("data-conn") != "live"
        page.evaluate(RESTORE)
        expect(control).to_have_text("Following", timeout=30000)


def test_on_reconnect_the_timeline_fills_the_gap_and_the_mark_clears(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-gap") as (_live_, page, name):
        before = _rows(page).count()
        page.evaluate(DROP)
        control = page.locator(CONTROL)
        expect(control).to_have_text("Not connected", timeout=8000)
        span_id = _stored_turn(name)
        page.wait_for_timeout(1500)
        assert _rows(page).count() == before
        page.evaluate(RESTORE)
        expect(control).to_have_text("Following", timeout=30000)
        expect(_rows(page)).to_have_count(before + 1)
        assert _newest(page).get_attribute("data-slug") == f"unmatched-{span_id}"
        assert page.locator(".stat.conn").get_attribute("data-conn") == "live"
        assert _in_view(page, _newest(page))


def test_when_the_run_ends_the_follow_control_and_the_pill_go_and_the_running_row_shows_how_the_turn_ended(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-done", filler=0, running=True) as (live, page, name):
        row = page.locator(f'#detail-panel .tl button[data-slug="{RUNNING}"]')
        assert ", running," in (row.get_attribute("aria-label") or "")
        _wheel_up(page, 50)
        _send(live, name, usd=2.0, slug=RUNNING, attrs=_turn_attrs(RUNNING, "Locked account returns 423.", 2.0, 1800))
        _end(live, name)
        expect(page.locator(CONTROL)).to_have_count(0, timeout=10000)
        expect(page.locator(PILL)).to_have_count(0)
        expect(page.locator(".newpill")).to_have_count(0)
        expect(row).to_have_attribute("aria-label", re.compile(r", finished,"))
        expect(row.locator(".m")).to_contain_text("$2.00")
        expect(row.locator(".w")).to_have_text("Locked account returns 423.")
        expect(page.locator(".rd .rd-head")).to_contain_text("finished")


def test_when_the_run_ends_the_headings_and_the_run_row_take_the_cost_of_that_last_turn(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-cost", filler=0, running=True) as (live, page, name):
        container = f"{name}-box"[:12].ljust(12, "x")
        headings = page.locator("#detail-panel .tl button.tl-group")
        assert "$" not in " ".join(headings.all_inner_texts())
        run_row = page.locator(f'#runs-list .row[data-worker-id="{container}"]')
        first_row = run_row.inner_text()
        _send(live, name, usd=2.0, slug=RUNNING, attrs=_turn_attrs(RUNNING, "Locked account returns 423.", 2.0, 1800))
        _end(live, name)
        expect(page.locator(CONTROL)).to_have_count(0, timeout=10000)
        for index in range(headings.count()):
            expect(headings.nth(index)).to_contain_text("$2.00")
        expect(run_row).to_contain_text("$2.00")
        assert run_row.inner_text() != first_row


def test_an_ended_run_opens_with_no_follow_control(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-old", filler=3, ended=True) as (_live_, page, _name):
        expect(_rows(page)).to_have_count(3)
        expect(page.locator(".feedbar")).to_have_count(0)
        expect(page.locator(CONTROL)).to_have_count(0)
        expect(page.locator(".newpill")).to_have_count(0)


def test_a_new_row_does_not_interrupt_a_focused_control_or_remount_an_open_reading_pane(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-focus", filler=3, running=True) as (live, page, name):
        expect(page.locator(".rd .at-text")).to_have_text("Rerunning the locked account scenario.")
        before = _rows(page).count()
        row = _rows(page).nth(1)
        row.focus()
        page.evaluate("() => { const body = document.querySelector('#detail-panel .rd-body'); window.__body = body; body.dataset.mark = 'kept'; window.__focus = document.activeElement; }")
        _arrive(live, name, 3)
        expect(_rows(page)).to_have_count(before + 3)
        page.wait_for_timeout(700)
        assert page.evaluate("() => document.activeElement === window.__focus && window.__focus.isConnected")
        assert page.evaluate("() => window.__body.isConnected && window.__body.dataset.mark") == "kept"
        control = page.locator(CONTROL)
        control.focus()
        _arrive(live, name, 2)
        expect(_rows(page)).to_have_count(before + 5)
        page.wait_for_timeout(700)
        assert page.evaluate("() => document.activeElement.classList.contains('follow')")


def test_the_follow_control_and_the_pill_have_a_role_a_name_keyboard_operation_and_the_count_is_announced_politely(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-a11y") as (live, page, name):
        control = page.get_by_role("button", name="Following")
        expect(control).to_have_count(1)
        assert not _scan(page)
        control.focus()
        page.keyboard.press("Enter")
        paused = page.get_by_role("button", name="Paused")
        expect(paused).to_have_attribute("aria-pressed", "false")
        page.keyboard.press("Space")
        expect(page.get_by_role("button", name="Following")).to_have_attribute("aria-pressed", "true")
        page.keyboard.press("Space")
        expect(page.get_by_role("button", name="Paused")).to_be_focused()
        _arrive(live, name, 2)
        pill = page.get_by_role("button", name=re.compile(r"^2 new"))
        expect(pill).to_have_count(1)
        assert page.locator(".newpill").get_attribute("aria-live") == "polite"
        assert not _scan(page)
        pill.focus()
        page.keyboard.press("Enter")
        expect(page.locator(PILL)).to_have_count(0)
        expect(page.get_by_role("button", name="Following")).to_be_focused()
        page.evaluate(DROP)
        expect(page.get_by_role("button", name="Not connected")).to_be_disabled(timeout=8000)
        assert not _scan(page)
        page.evaluate(RESTORE)


def _selected_slug(page) -> str:
    return page.locator("#detail-panel .tl button[aria-current=true]").get_attribute("data-slug")


def test_the_pill_selects_the_newest_row_and_opens_it_in_the_pane(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-pick") as (live, page, name):
        older = _rows(page).nth(1)
        older.click()
        older_slug = older.get_attribute("data-slug")
        expect(older).to_have_attribute("aria-current", "true")
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        last = _arrive(live, name, 3)
        expect(page.locator(PILL)).to_contain_text("3 new")
        assert _selected_slug(page) == older_slug
        page.locator(PILL).click()
        newest = f"unmatched-{last[-1]}"
        expect(page.locator(f'#detail-panel .tl button[data-slug="{newest}"]')).to_have_attribute("aria-current", "true")
        assert page.locator("#detail-panel .tl button[aria-current=true]").count() == 1
        expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
        expect(page.locator(".rd .rd-body")).to_contain_text("No record of this turn")
        expect(page.locator(CONTROL)).to_have_text("Following")


def test_scrolling_back_to_the_end_leaves_the_selection_alone(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-keep1") as (live, page, name):
        older = _rows(page).nth(1)
        older.click()
        older_slug = older.get_attribute("data-slug")
        _wheel_up(page)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        _arrive(live, name, 2)
        expect(page.locator(PILL)).to_contain_text("2 new")
        page.locator(LIST).evaluate("el => { el.scrollTop = el.scrollHeight; }")
        expect(page.locator(CONTROL)).to_have_text("Following")
        page.wait_for_timeout(400)
        assert _selected_slug(page) == older_slug
        _arrive(live, name, 1)
        page.wait_for_timeout(600)
        assert _selected_slug(page) == older_slug


def test_pressing_the_control_to_resume_leaves_the_selection_alone(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-keep2") as (live, page, name):
        older = _rows(page).nth(1)
        older.click()
        older_slug = older.get_attribute("data-slug")
        control = page.locator(CONTROL)
        if control.inner_text() == "Following":
            control.click()
        expect(control).to_have_text("Paused")
        _arrive(live, name, 2)
        expect(page.locator(PILL)).to_contain_text("2 new")
        control.click()
        expect(control).to_have_text("Following")
        page.wait_for_timeout(400)
        assert _selected_slug(page) == older_slug
        _arrive(live, name, 1)
        page.wait_for_timeout(600)
        assert _selected_slug(page) == older_slug


def test_the_pill_brings_the_newest_row_into_view_when_a_later_group_sits_below_it(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-later", turns=True, running=True, height=330) as (live, page, name):
        assert page.locator("#detail-panel .tl button.tl-group").count() >= 2
        closed = page.locator("#detail-panel .tl button[aria-expanded=false]")
        while closed.count():
            closed.first.click()
        _wheel_up(page, 2000)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        last = _arrive(live, name, 3)
        expect(page.locator(PILL)).to_contain_text("3 new")
        page.locator(PILL).click()
        expect(page.locator(CONTROL)).to_have_text("Following")
        newest = page.locator(f'#detail-panel .tl button[data-slug="unmatched-{last[-1]}"]')
        expect(newest).to_have_count(1)
        assert _uncovered(page, newest)
        assert not (_newest(page).get_attribute("data-slug") or "").startswith("unmatched-"), "a later group must sit below the newest row for this test to mean anything"
        _arrive(live, name, 2)
        expect(page.locator(PILL)).to_have_count(0)
        page.wait_for_timeout(600)
        assert _uncovered(page, page.locator("#detail-panel .tl button[data-slug^=unmatched-]").last)


def test_the_flow_heading_sticks_exactly_under_the_group_heading_so_no_row_shows_between(tmp_path):
    with _following(tmp_path, "fol-stick", turns=True, running=True) as (_live_, page, _name):
        page.locator(LIST).evaluate("el => { el.scrollTop = 200; }")
        page.wait_for_timeout(300)
        gap = page.evaluate(
            """(list) => {
              const sec = document.querySelector(list + ' .tl-sec');
              const group = sec.querySelector(':scope > .tl-group').getBoundingClientRect();
              const flow = sec.querySelector('.tl-sub > .tl-flow').getBoundingClientRect();
              const hit = document.elementFromPoint(flow.left + 40, group.bottom + 0.5);
              return { gap: flow.top - group.bottom, atEdge: !!hit && hit.closest('.tl-flow') !== null };
            }""",
            LIST,
        )
        assert abs(gap["gap"]) <= 0.5, gap
        assert gap["atEdge"], gap


def test_a_run_that_ends_with_no_turn_span_stops_saying_running(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-kill", filler=0, turns=True, running=True) as (live, page, name):
        row = page.locator(f'#detail-panel .tl button[data-slug="{RUNNING}"]')
        row.click()
        expect(page.locator(".rd .rd-head .chip")).to_have_text(re.compile("running", re.I))
        heads = page.locator("#detail-panel .tl button.tl-group, #detail-panel .tl button.tl-flow")
        before = " ".join(heads.all_inner_texts())
        assert "running" in before
        spent = re.findall(r"\$[\d.]+", before)
        _end(live, name)
        expect(page.locator(CONTROL)).to_have_count(0, timeout=10000)
        expect(row).to_have_attribute("aria-label", re.compile(r", ended with no record,"))
        expect(row.locator(".w")).to_have_text("ended with no record")
        expect(row.locator(".m")).to_have_text("")
        expect(row.locator(".i")).not_to_have_text("●")
        assert "live" not in (row.get_attribute("class") or "")
        expect(page.locator(".rd .rd-head .chip")).to_have_text(re.compile("no record", re.I))
        expect(page.locator(".rd .rd-head .dot")).not_to_have_class(re.compile("running"))
        head = page.locator(".rd .rd-head").inner_text()
        assert "lands at turn end" not in head
        assert "running" not in head.lower()
        body = page.locator(".rd .rd-body")
        expect(body).to_contain_text("This turn ended with no record, so its cost was not reported.")
        expect(body).to_contain_text("Rerunning the locked account scenario.")
        assert body.inner_text().index("ended with no record") < body.inner_text().index("Rerunning")
        after = " ".join(heads.all_inner_texts())
        assert "running" not in after
        assert re.findall(r"\$[\d.]+", after) == spent
        assert "$0.00" not in head


def test_the_connection_chip_says_not_connected_once_the_connection_is_offline(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "fol-chip") as (_live_, page, _name):
        chip = page.locator(".stat.conn")
        expect(chip).to_have_text("live")
        page.evaluate(DROP)
        expect(chip).to_have_text("reconnecting", timeout=8000)
        assert "reconnecting" in chip.get_attribute("aria-label")
        page.evaluate(LONG_LOSS)
        expect(chip).to_have_text("not connected", timeout=8000)
        expect(chip).to_have_attribute("aria-label", "Connection: not connected")
        expect(chip).to_have_attribute("data-conn", "offline")
        expect(page.locator(CONTROL)).to_have_text("Not connected")
        page.evaluate(RESTORE)
        expect(chip).to_have_text("live", timeout=30000)
