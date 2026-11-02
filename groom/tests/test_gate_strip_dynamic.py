"""The gate strip above the tabs and the Runs rail badge, measured on the page the operator gets."""
from __future__ import annotations

import json
import tempfile
import time
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _box,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_breakdown_dynamic import CONTAINER, RUN, _pick_run, _seeded, _span

FIRST = "Keep the legacy CSV header order, or switch and update both reports?"
SECOND = "Should the changelog mention the new header order?"

PLACE = """() => {
  const scroller = document.querySelector('#detail-panel > .ov');
  const target = document.querySelector('[data-place]');
  const box = scroller.getBoundingClientRect();
  const at = target.getBoundingClientRect();
  return { top: at.top, bottom: at.bottom, from: box.top, to: box.bottom, scrollTop: scroller.scrollTop,
           room: scroller.scrollHeight - scroller.clientHeight };
}"""

MARK = """() => {
  const scroller = document.querySelector('#detail-panel > .ov').getBoundingClientRect();
  const rows = [...document.querySelectorAll('#detail-panel table.tt tbody tr')];
  const fits = rows.filter((el) => {
    const box = el.getBoundingClientRect();
    return box.top >= scroller.top + 300 && box.bottom <= scroller.bottom - 20;
  });
  fits[0].dataset.place = 'kept';
}"""

WATCH = """() => {
  const target = document.querySelector('[data-place]');
  window.__seen = [];
  const frame = () => {
    window.__seen.push(target.isConnected ? target.getBoundingClientRect().top : null);
    window.__frames = requestAnimationFrame(frame);
  };
  frame();
}"""


def _gate_file(directory: Path, name: str, question: str) -> str:
    path = directory / name
    path.write_text(f"STATUS: AWAITING_OPERATOR\n\n## Question from the agent\n\n{question}\n")
    return str(path)


def _post(live, route: str, body: dict) -> None:
    request = urllib.request.Request(
        live.url() + route.lstrip("/"),
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as reply:
        assert reply.status in (200, 201)


def _open_gate(live, path: str, question: str, container: str = CONTAINER) -> None:
    _post(live, "/push/blocked", {"container_id": container, "file_path": path, "question": question})


def _long_run() -> None:
    from groom import store

    now = time.time()
    store.insert_spans(
        [
            _span(f"pad-{index}", RUN, "it-state", f"pad-{index}", f"pad-{index}", now - 800 + index, 1.0, {"workhorse.depth": 1})
            for index in range(30)
        ]
    )


@contextmanager
def _gated() -> Iterator[Path]:
    from groom import app as app_module
    from groom import state

    state.RUNS.pop(RUN, None)
    with (
        tempfile.TemporaryDirectory() as tmp,
        _seeded(),
        patch.object(app_module, "_sync_native_row", lambda *_: False),
    ):
        _long_run()
        try:
            yield Path(tmp)
        finally:
            state.RUNS.pop(RUN, None)


def _strip(page):
    return page.get_by_role("region", name="Open gates")


def _place(page) -> dict:
    return page.evaluate(PLACE)


def _scroll_overview(page, to: int) -> None:
    page.evaluate("(to) => { document.querySelector('#detail-panel > .ov').scrollTop = to; }", to)
    page.wait_for_timeout(100)


def _show_overview(page) -> None:
    page.set_viewport_size({"width": 1400, "height": 960})
    _pick_run(page, RUN)
    page.get_by_role("button", name="Expand work").click()
    page.wait_for_function(
        "() => { const el = document.querySelector('#detail-panel > .ov');"
        " return !!el && el.scrollHeight - el.clientHeight > 250 && !!document.querySelector('#detail-panel table.tt tbody tr:nth-child(3)'); }",
        timeout=15000,
    )


def _read_overview(page, to: int = 320) -> dict:
    _show_overview(page)
    _scroll_overview(page, to)
    page.evaluate(MARK)
    before = _place(page)
    assert before["scrollTop"] > 0, before
    return before


def _held(page, before: dict) -> dict:
    now = _place(page)
    assert abs(now["top"] - before["top"]) <= 1.5, (before, now)
    assert now["from"] <= now["top"] and now["bottom"] <= now["to"], now
    return now


def test_the_strip_stays_above_the_tabs_while_a_tab_scrolls():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        page = _open(live)
        try:
            _show_overview(page)
            strip = _strip(page)
            strip.wait_for()
            at = _box(strip)
            assert at["y"] + at["height"] <= _box(page.get_by_role("tablist"))["y"] + 1
            assert _box(page.get_by_role("tablist"))["y"] < _box(page.get_by_role("tabpanel"))["y"]
            _scroll_overview(page, 200)
            assert page.evaluate("() => document.querySelector('#detail-panel > .ov').scrollTop") > 0
            assert _box(strip) == at
            assert strip.get_by_role("textbox").is_visible()
            assert not _scan(page)
        finally:
            page.close()


def test_a_gate_that_opens_while_the_operator_reads_leaves_the_text_where_it_was():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        page = _open(live)
        try:
            before = _read_overview(page)
            page.evaluate(WATCH)
            _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
            expect(_strip(page)).to_contain_text("legacy CSV header order")
            page.wait_for_timeout(300)
            _held(page, before)
            seen = page.evaluate("() => { cancelAnimationFrame(window.__frames); return window.__seen; }")
            assert seen and all(top is not None and abs(top - before["top"]) <= 1.5 for top in seen), seen
        finally:
            page.close()


def test_two_open_gates_both_show_with_their_own_question_and_box():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        _open_gate(live, _gate_file(tmp, "2-two.md", SECOND), SECOND)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            strip = _strip(page)
            expect(strip).to_contain_text("legacy CSV header order")
            expect(strip).to_contain_text("changelog mention")
            expect(strip.get_by_role("textbox", name="Your answer")).to_have_count(2)
            expect(strip.get_by_role("button", name="Send answer")).to_have_count(2)
            expect(strip.get_by_role("button", name="Collapse")).to_have_count(1)
            first = strip.locator(".gate-block").first
            expect(first.get_by_role("button", name="Collapse")).to_have_count(1)
            assert _box(strip)["y"] < _box(page.get_by_role("tablist"))["y"]
            assert not _scan(page)
        finally:
            page.close()


def test_the_strip_collapses_to_one_line_with_the_start_of_the_question_and_expands_again():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        page = _open(live)
        try:
            before = _read_overview(page)
            strip = _strip(page)
            full = _box(strip)["height"]
            strip.get_by_role("textbox").fill("half a thought")
            strip.get_by_role("button", name="Collapse").click()
            expect(strip.get_by_role("textbox")).to_have_count(0)
            expect(strip.get_by_role("button", name="Answer", exact=True)).to_have_attribute("aria-expanded", "false")
            expect(strip).to_contain_text("Keep the legacy CSV header order")
            assert _box(strip)["height"] < full / 2, (_box(strip), full)
            assert not _scan(page)
            page.wait_for_timeout(300)
            _held(page, before)
            strip.get_by_role("button", name="Answer", exact=True).click()
            textbox = strip.get_by_role("textbox")
            expect(textbox).to_have_value("half a thought")
            expect(textbox).to_be_focused()
            page.wait_for_timeout(300)
            _held(page, before)
            assert _box(strip)["height"] == full
        finally:
            page.close()


def test_a_gate_that_opens_while_collapsed_is_counted_on_the_collapsed_line():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            strip = _strip(page)
            strip.get_by_role("button", name="Collapse").click()
            expect(strip.get_by_role("textbox")).to_have_count(0)
            expect(strip).not_to_contain_text("gates open")
            _open_gate(live, _gate_file(tmp, "2-two.md", SECOND), SECOND)
            expect(strip).to_contain_text("2 gates open")
            expect(strip.get_by_role("textbox")).to_have_count(0)
            strip.get_by_role("button", name="Answer", exact=True).click()
            expect(strip.get_by_role("textbox", name="Your answer")).to_have_count(2)
        finally:
            page.close()


def test_a_live_push_keeps_the_draft_the_collapsed_state_and_the_focused_gate():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        _open_gate(live, _gate_file(tmp, "2-two.md", SECOND), SECOND)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            boxes = _strip(page).get_by_role("textbox", name="Your answer")
            boxes.nth(0).fill("first draft")
            boxes.nth(1).fill("second draft, still being typed")
            boxes.nth(1).focus()
            page.keyboard.press("Home")
            page.keyboard.press("Shift+End")
            _open_gate(live, _gate_file(tmp, "3-three.md", "A third question?"), "A third question?")
            expect(boxes).to_have_count(3)
            expect(boxes.nth(0)).to_have_value("first draft")
            expect(boxes.nth(1)).to_have_value("second draft, still being typed")
            expect(boxes.nth(1)).to_be_focused()
            selected = page.evaluate("() => document.getSelection().toString() || document.activeElement.value.slice(document.activeElement.selectionStart, document.activeElement.selectionEnd)")
            assert selected == "second draft, still being typed", selected
            _strip(page).get_by_role("button", name="Collapse").click()
            _open_gate(live, _gate_file(tmp, "4-four.md", "A fourth question?"), "A fourth question?")
            expect(_strip(page)).to_contain_text("4 gates open")
            expect(boxes).to_have_count(0)
            _strip(page).get_by_role("button", name="Answer", exact=True).click()
            expect(boxes).to_have_count(4)
            expect(boxes.nth(1)).to_have_value("second draft, still being typed")
        finally:
            page.close()


def test_sending_an_answer_removes_that_gate_and_the_last_one_clears_the_strip_without_moving_the_tab():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        first = _gate_file(tmp, "1-one.md", FIRST)
        second = _gate_file(tmp, "2-two.md", SECOND)
        _open_gate(live, first, FIRST)
        _open_gate(live, second, SECOND)
        page = _open(live)
        try:
            before = _read_overview(page, 560)
            page.get_by_role("tab", name="Overview").focus()
            strip = _strip(page)
            strip.get_by_role("textbox").nth(0).fill("keep it")
            strip.get_by_role("button", name="Send answer").nth(0).click()
            expect(strip.get_by_role("textbox")).to_have_count(1)
            expect(strip).not_to_contain_text("legacy CSV header order")
            expect(strip).to_contain_text("changelog mention")
            assert "keep it" in Path(first).read_text()
            expect(page.get_by_role("tab", name="Overview")).to_have_attribute("aria-selected", "true")
            page.wait_for_timeout(300)
            _held(page, before)
            strip.get_by_role("textbox").fill("yes")
            strip.get_by_role("button", name="Send answer").click()
            expect(_strip(page)).to_have_count(0)
            assert "yes" in Path(second).read_text()
            expect(page.get_by_role("tab", name="Overview")).to_have_attribute("aria-selected", "true")
            page.wait_for_timeout(300)
            _held(page, before)
            assert _place(page)["scrollTop"] >= 0
        finally:
            page.close()


def test_sending_an_answer_keeps_the_details_tab_open():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            page.get_by_role("tab", name="Details").click()
            strip = _strip(page)
            strip.get_by_role("textbox").fill("go")
            strip.get_by_role("button", name="Send answer").click()
            expect(_strip(page)).to_have_count(0)
            expect(page.get_by_role("tab", name="Details")).to_have_attribute("aria-selected", "true")
            expect(page.get_by_role("tabpanel")).to_contain_text("Metrics")
        finally:
            page.close()


def test_a_failed_send_keeps_the_typed_answer_and_says_it_failed():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        missing = str(tmp / "gone.md")
        _open_gate(live, missing, FIRST)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            strip = _strip(page)
            strip.get_by_role("textbox").fill("sqlite, please")
            strip.get_by_role("button", name="Send answer").click()
            toast = page.locator("#toasts .toast.blocked")
            expect(toast).to_have_count(1)
            assert toast.inner_text().splitlines() == ["✗ answer not taken", "gate file not found"]
            expect(strip.get_by_role("textbox")).to_have_value("sqlite, please")
            expect(strip).to_contain_text("Keep the legacy CSV header order")
        finally:
            page.close()


def test_shortcut_keys_typed_in_the_answer_box_do_nothing_else():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            box = _strip(page).get_by_role("textbox")
            box.focus()
            page.keyboard.type("jjkk jk")
            expect(box).to_have_value("jjkk jk")
            expect(page.locator("#runs-list .row[aria-current='true']")).to_contain_text(RUN)
            expect(box).to_be_focused()
            assert page.evaluate("() => document.querySelector('.app').dataset.mode") == "runs"
        finally:
            page.close()


def test_an_unsafe_question_is_sanitized_before_it_reaches_the_strip():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    unsafe = (
        'Pick **one**\n\n<img src=x onerror="window.__pwn = 1">\n\n<script>window.__pwn = 2</script>\n\n'
        '[take me](javascript:window.__pwn=3)\n\n<iframe src="about:blank"></iframe>'
    )
    with _gated() as tmp:
        _open_gate(live, _gate_file(tmp, "1-one.md", "x"), unsafe)
        page = _open(live)
        try:
            _pick_run(page, RUN)
            strip = _strip(page)
            expect(strip.locator("strong")).to_have_text("one")
            page.wait_for_timeout(300)
            assert strip.locator("script, iframe").count() == 0
            assert strip.locator("[onerror], [onclick]").count() == 0
            hrefs = strip.locator("a").evaluate_all("els => els.map(e => e.getAttribute('href'))")
            assert not [href for href in hrefs if href and href.lower().startswith("javascript")], hrefs
            assert page.evaluate("() => window.__pwn") is None
        finally:
            page.close()


def _badge(page):
    return page.locator("#activitybar .act-btn[data-mode='runs'] .rail-badge")


def _blocked_count(page) -> int:
    return int(page.locator("#statusbar .stat", has_text="blocked").locator(".n").inner_text())


@contextmanager
def _nothing_blocked() -> Iterator[None]:
    from groom import state

    held = {cid: (wf, dict(vars(wf)), dict(wf.gates)) for cid, wf in state.WORKFLOWS.items()}
    try:
        yield
    finally:
        for cid, (wf, fields, gates) in held.items():
            vars(wf).update(fields)
            wf.gates = gates
            state.WORKFLOWS[cid] = wf


def test_the_runs_button_carries_a_counted_badge_while_another_pane_is_open_and_clears_with_the_last_block():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _gated() as tmp, _nothing_blocked():
        page = _open(live)
        try:
            expect(_badge(page)).to_have_count(1)
            expect(_badge(page)).to_be_hidden()
            blocked = _blocked_count(page)
            assert blocked >= 1
            page.click(".act-btn[data-mode='attend']")
            expect(_badge(page)).to_be_visible()
            expect(_badge(page)).to_have_text(str(blocked))
            noun = "blocked run" if blocked == 1 else "blocked runs"
            button = page.get_by_role("button", name=f"Runs, {blocked} {noun}")
            expect(button).to_have_count(1)
            assert not _scan(page)
            _open_gate(live, _gate_file(tmp, "1-one.md", FIRST), FIRST)
            expect(_badge(page)).to_have_text(str(blocked + 1))
            expect(page.get_by_role("button", name=f"Runs, {blocked + 1} blocked runs")).to_have_count(1)
            page.click(".act-btn[data-mode='runs']")
            expect(_badge(page)).to_be_hidden()
            page.click(".act-btn[data-mode='settings']")
            expect(_badge(page)).to_be_visible()
            from groom import state

            for cid in list(state.WORKFLOWS):
                _post(live, "/push/exited", {"container_id": cid[:12], "exit_code": 0})
            expect(_badge(page)).to_be_hidden()
            expect(page.get_by_role("button", name="Runs", exact=True)).to_have_count(1)
        finally:
            page.close()
