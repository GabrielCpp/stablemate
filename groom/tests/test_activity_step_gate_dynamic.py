"""A step and an operator gate read in the Activity tab, measured on the page the operator gets."""
from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from test_activity_groups import BASE, _attrs, _seed
from test_activity_tab_dynamic import _open_activity, _pick, _rows, _run
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_run_clock import span

from groom import state, store

ASKED = "Should a locked account answer 401 or 423?"
GATE = "gates/qa-story.md"
ERROR_TEXT = "docker compose up exited 1\nError: bind for 0.0.0.0:5432 failed: port is already allocated"
HOSTILE = "<img src=x onerror=\"window.__ran=1\"><script>window.__ran=1</script>"


def _insert_logs(node: str, at: float, lines: list[tuple[str, str]]) -> None:
    store.insert_logs([
        {"run_id": run_id, "node": node, "severity": level, "body": body, "ts": at + number}
        for run_id, number, (level, body) in ((_CURRENT[0], number, line) for number, line in enumerate(lines))
    ])


_CURRENT = [""]


def _telemetry(run: str, node: str, *, wait: str = "") -> None:
    from groom.models import RunTelemetry

    now = time.time()
    state.RUNS[run] = RunTelemetry(
        run_id=run, workflow="coder", current_node=node, node_elapsed_s=900.0, wait_kind=wait,
        wait_elapsed_s=720.0 if wait else 0.0, wait_gate_path=GATE if wait else "", wait_gate_question=ASKED if wait else "",
        turn_active=False, last_heartbeat_ts=now, last_span_ts=now, first_seen_ts=now - 1000, last_telemetry_ts=now,
        gauge_ts={"workhorse.wait.elapsed_s": now, "workhorse.node.elapsed_s": now, "workhorse.turn.elapsed_s": now},
    )


@contextmanager
def _stepped(run: str, tmp: Path, *, gate: str = "", running: bool = False, answer: str = "Use 423, and say why in the body.") -> Iterator[str]:
    with _run(run, tmp, turns=False) as name:
        _CURRENT[0] = name
        _seed(name)
        failed = span("e1", "t1", "sa", "ensure_stack", "ensure_stack", BASE + 42.2, 4, {"error.class": "StackStartFailed", "status_message": ERROR_TEXT} | _attrs("sign-in"), 1, name) | {"status": "ERROR"}
        silent = span("e2", "t1", "sa", "run_gate", "run_gate", BASE + 60, 62, {"error.class": "GateFailed", "status_message": "2 scenarios failed: expired code, locked account"} | _attrs("sign-in"), 1, name) | {"status": "ERROR"}
        spans = [failed, silent]
        waiting = {"workhorse.span_kind": "wait", "workhorse.wait_kind": "operator", "workhorse.gate_path": GATE, "workhorse.gate_question": ASKED, "workhorse.wait_outcome": "completed"}
        if gate == "answered":
            spans.append(span("w1", "t1", "sa", "qa-story", "wait:operator", BASE + 100, 540, waiting | _attrs("sign-in"), 1, name))
        store.insert_spans(spans)
        _insert_logs("ensure_stack", BASE + 42.5, [("INFO", "starting stack api-service"), ("INFO", "compose project qa-sign-in"), ("ERROR", "port 5432 already in use")])
        _insert_logs("lint", BASE + 13, [("INFO", "clean " + HOSTILE)])
        directory = tmp / "ws" / "gates"
        directory.mkdir(parents=True, exist_ok=True)
        if gate == "answered":
            (directory / "qa-story.md").write_text(f"STATUS: ANSWERED\n\n## Questions from the agent\n\n{ASKED}\n\n{answer}\n")
        elif gate == "open":
            (directory / "qa-story.md").write_text(f"STATUS: AWAITING_OPERATOR\n\n## Questions from the agent\n\n{ASKED}\n")
            _telemetry(name, "qa-story", wait="operator")
        if running:
            _telemetry(name, "prepare_fixtures")
            _insert_logs("prepare_fixtures", time.time() - 5, [("INFO", "copying fixtures into the stack")])
        try:
            yield name
        finally:
            state.RUNS.pop(name, None)


def _reveal(page) -> None:
    closed = page.locator("#detail-panel .tl button[aria-expanded=false]")
    for _ in range(30):
        if not closed.count():
            return
        closed.first.click()


def _reading(page, run: str, key: str):
    _pick(page, run)
    _open_activity(page)
    _reveal(page)
    page.locator(f'#detail-panel .tl button[data-entry="{key}"]').click()
    return page.locator("#detail-panel .rd[data-reading]")


def _with(tmp_path: Path, run: str, key: str, check, **given) -> None:
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped(run, tmp_path, **given) as name:
        page = _open(live)
        try:
            check(page, _reading(page, name, key))
        finally:
            page.close()


def test_a_failed_step_opens_a_pane_naming_the_step_work_item_pass_duration_and_error_class(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        head = pane.locator(".rd-head")
        expect(head).to_contain_text("ensure_stack")
        expect(head).to_contain_text("sign-in")
        expect(head).to_contain_text("failed")
        expect(head).to_contain_text("qa · 1st pass · step")
        expect(head).to_contain_text("4s")
        expect(head).to_contain_text("error StackStartFailed")

    _with(tmp_path, "step-head", "failed:e1", check)


def test_the_full_error_text_is_shown_and_marked_as_an_error_in_words(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".err-role")).to_have_text(re.compile(r"Error"))
        box = pane.locator(".err-box")
        assert box.inner_text() == ERROR_TEXT
        assert box.get_attribute("aria-label") == "Error"

    _with(tmp_path, "step-error", "failed:e1", check)


def test_the_logs_of_the_step_show_time_level_node_and_message(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        lines = pane.locator(".log-line")
        expect(lines).to_have_count(3)
        expect(pane.locator(".sec-h")).to_contain_text("Logs from this step")
        first = lines.nth(0)
        assert re.fullmatch(r"\d\d:\d\d:\d\d", first.locator(".lt-ts").inner_text())
        assert first.locator(".lt-lvl").inner_text() == "INFO"
        assert first.locator(".lt-node").inner_text() == "ensure_stack"
        assert first.locator(".lt-body").inner_text() == "starting stack api-service"

    _with(tmp_path, "step-logs", "failed:e1", check)


def test_an_error_log_line_differs_from_the_others_by_more_than_its_color(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".log-line")).to_have_count(3)
        weights = pane.locator(".log-line .lt-lvl").evaluate_all("(els) => els.map((el) => [el.innerText, getComputedStyle(el).fontWeight, el.parentElement.className])")
        info, error = weights[0], weights[2]
        assert (info[0], error[0]) == ("INFO", "ERROR")
        assert "bad" in error[2] and "bad" not in info[2]
        assert int(error[1]) > int(info[1])

    _with(tmp_path, "step-bad-line", "failed:e1", check)


def test_a_step_with_no_logs_says_it_recorded_none(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".log-line")).to_have_count(0)
        expect(pane).to_contain_text("This step recorded no logs.")
        expect(pane.locator(".err-box")).to_contain_text("2 scenarios failed")

    _with(tmp_path, "step-nologs", "failed:e2", check)


def test_the_pane_says_what_came_next_and_its_control_opens_that_row_in_the_timeline(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.get_by_text("What came next")).to_be_visible()
        expect(pane).to_contain_text("qa-story ran next, an agent turn.")
        page.get_by_role("button", name="Open that turn").click()
        expect(page.locator("#detail-panel .tl button[aria-current=true]")).to_have_attribute("data-slug", re.compile(r"."))
        expect(page.locator("#detail-panel .tl button[aria-current=true]")).to_have_attribute("aria-label", re.compile(r"^qa-story,"))

    _with(tmp_path, "step-next", "failed:e1", check)


def test_a_step_followed_by_a_gate_offers_to_open_that_gate_and_it_opens(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane).to_contain_text("The run stopped at operator gate next.")
        page.get_by_role("button", name="Open that gate").click()
        expect(page.locator("#detail-panel .rd[data-reading=gate]")).to_be_visible()
        expect(page.locator("#detail-panel .tl button[aria-current=true]")).to_have_attribute("data-entry", "gate:qa-story#1")

    _with(tmp_path, "step-to-gate", "failed:e2", check, gate="answered")


def test_a_running_step_says_it_is_running_and_that_nothing_has_come_next(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".rd-head .chip")).to_have_text("running")
        expect(pane).to_contain_text("Nothing yet. This is still running.")
        expect(pane.locator(".log-line")).to_have_count(1)
        row = page.locator('#detail-panel .tl button[data-entry="step:running:prepare_fixtures"]')
        expect(row).to_have_attribute("data-kind", "doing")
        expect(row).to_contain_text("running")
        expect(pane.get_by_role("button", name=re.compile("Open that"))).to_have_count(0)

    _with(tmp_path, "step-running", "step:running:prepare_fixtures", check, running=True)


def test_a_passed_step_shows_its_logs_and_what_came_next(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".rd-head .chip")).to_have_text("passed")
        expect(pane.locator(".log-line")).to_have_count(1)
        expect(pane).to_contain_text("build ran next and passed.")
        expect(pane.locator(".err-box")).to_have_count(0)

    _with(tmp_path, "step-passed", "step:a-lint", check)


def test_an_answered_gate_shows_the_question_the_answer_when_it_was_answered_and_how_long_it_waited(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".rd-head .chip")).to_have_text("answered in 9m")
        expect(pane.locator(".rd-head")).to_contain_text(GATE)
        expect(pane.locator(".at-msg").nth(0)).to_contain_text("Question")
        expect(pane.locator(".at-msg").nth(0)).to_contain_text(ASKED)
        answer = pane.locator(".at-msg.user")
        expect(answer).to_contain_text("Use 423, and say why in the body.")
        assert re.search(r"your answer · \d\d:\d\d", answer.inner_text(), re.IGNORECASE)

    _with(tmp_path, "gate-answered", "gate:qa-story#1", check, gate="answered")


def test_an_open_gate_shows_its_question_and_how_long_it_has_waited(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".rd-head .chip")).to_have_text(re.compile(r"^waiting 1[2-3]m"))
        expect(pane.locator(".at-msg").nth(0)).to_contain_text(ASKED)

    _with(tmp_path, "gate-open", "gate:qa-story#1", check, gate="open")


def test_an_open_gate_says_it_is_not_answered_and_points_to_the_box_above_the_tabs(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane).to_contain_text("Not answered yet. Answer in the box above the tabs.")
        expect(pane.locator("form[data-answer], textarea")).to_have_count(0)
        expect(page.locator("form[data-answer] textarea")).to_have_count(1)
        above = page.evaluate("() => document.querySelector('form[data-answer]').getBoundingClientRect().bottom <= document.querySelector('#detail .dtabs').getBoundingClientRect().top")
        assert above

    _with(tmp_path, "gate-pointer", "gate:qa-story#1", check, gate="open")


def test_answering_in_the_box_above_the_tabs_turns_the_pane_answered_and_keeps_the_selection(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        selected = page.locator("#detail-panel .tl button[aria-current=true]")
        expect(selected).to_have_attribute("data-entry", "gate:qa-story#1")
        page.locator("form[data-answer] textarea").fill("Use 423.")
        page.get_by_role("button", name="Send answer").click()
        expect(pane.locator(".at-msg.user")).to_contain_text("Use 423.")
        expect(selected).to_have_attribute("data-entry", "gate:qa-story#1")
        expect(pane.locator(".rd-head .chip")).to_contain_text("answered")

    _with(tmp_path, "gate-answer", "gate:qa-story#1", check, gate="open")


def test_a_step_being_read_shows_a_reading_state_that_clears_when_it_appears(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("step-wait", tmp_path) as name:
        page = _open(live)
        held = []
        page.route(re.compile(r"/entry/"), lambda route: held.append(route))
        try:
            _pick(page, name)
            _open_activity(page)
            _reveal(page)
            page.locator('#detail-panel .tl button[data-entry="failed:e1"]').click()
            reading = page.locator(".rd .detail-empty.loading")
            expect(reading).to_have_attribute("aria-busy", "true")
            expect(reading).to_contain_text("Reading this step")
            while not held:
                page.wait_for_timeout(50)
            held[0].continue_()
            expect(reading).to_have_count(0)
            expect(page.locator(".rd .rd-head")).to_contain_text("ensure_stack")
        finally:
            page.close()


def test_a_step_that_cannot_be_read_says_so_keeps_its_row_and_a_retry_replaces_it_with_the_details(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("step-bad", tmp_path) as name:
        page = _open(live)
        failing = {"on": True}

        def handle(route):
            if failing["on"]:
                route.fulfill(status=503, body="{}", content_type="application/json")
            else:
                route.continue_()

        page.route(re.compile(r"/entry/"), handle)
        try:
            _pick(page, name)
            _open_activity(page)
            _reveal(page)
            row = page.locator('#detail-panel .tl button[data-entry="failed:e1"]')
            row.click()
            expect(page.locator(".rd .side-state")).to_contain_text("The details of this step could not be read")
            expect(page.locator(".rd .side-state")).to_contain_text("The row in the timeline stays.")
            expect(row).to_have_attribute("aria-current", "true")
            expect(row).to_contain_text("ensure_stack")
            failing["on"] = False
            page.get_by_role("button", name="Retry now").click()
            expect(page.locator(".rd .side-state")).to_have_count(0)
            expect(page.locator(".rd .rd-head")).to_contain_text("ensure_stack")
            expect(page.locator(".rd .err-box")).to_contain_text("port is already allocated")
        finally:
            page.close()


def test_html_in_a_log_line_or_an_answer_renders_as_text_and_no_script_runs(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".log-line .lt-body")).to_contain_text("<script>")
        assert pane.locator("img, script").count() == 0
        assert page.evaluate("() => window.__ran === undefined")
        page.get_by_role("button", name="Open that step").click()
        expect(page.locator(".rd .rd-head")).to_contain_text("build")
        assert page.evaluate("() => window.__ran === undefined")

    _with(tmp_path, "step-hostile", "step:a-lint", check)


def test_the_hostile_gate_answer_renders_without_markup_or_script(tmp_path):
    from playwright.sync_api import expect

    def check(page, pane):
        expect(pane.locator(".at-msg.user")).to_contain_text("423")
        assert pane.locator("img, script").count() == 0
        assert page.evaluate("() => window.__ran === undefined")

    _with(tmp_path, "gate-hostile", "gate:qa-story#1", check, gate="answered", answer="423 " + HOSTILE)


def test_the_controls_of_the_new_panes_have_a_role_a_name_keyboard_operation_and_axe_is_clean(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _stepped("step-a11y", tmp_path, gate="open", running=False) as name:
        page = _open(live)
        try:
            _pick(page, name)
            _open_activity(page)
            _reveal(page)
            for key in ("failed:e1", "failed:e2", "step:a-lint", "gate:qa-story#1"):
                _telemetry(name, "qa-story", wait="operator")
                _reveal(page)
                row = page.locator(f'#detail-panel .tl button[data-entry="{key}"]')
                assert (row.get_attribute("aria-label") or "").strip()
                row.focus()
                page.keyboard.press("Enter")
                expect(row).to_have_attribute("aria-current", "true")
                expect(page.locator("#detail-panel .rd[data-reading]")).to_be_visible()
                assert _scan(page) == [], key
            page.locator('#detail-panel .tl button[data-entry="failed:e1"]').focus()
            page.keyboard.press("Space")
            nxt = page.get_by_role("button", name="Open that turn")
            nxt.focus()
            page.keyboard.press("Enter")
            expect(page.locator("#detail-panel .tl button[aria-current=true]")).to_have_attribute("data-slug", re.compile(r"."))
            assert len(_rows(page).all()) > 0
        finally:
            page.close()
