"""The Activity tab of a run, measured on the page the operator gets, over real spans, real archived records and a real live transcript."""
from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_run_clock import STATE, span

SESSION = "sess-1"
FIRST = "001-00001-document-story"
SECOND = "001-00002-qa-story"
RUNNING = "001-00003-qa-story"
HTML_TEXT = '<img src=x onerror="window.__pwned=1"><script>window.__pwned=1</script>'
MARKDOWN_IMAGE = "![remote logo](http://127.0.0.1:9/pixel.png)"
RICH_TEXT = "**Bold claim** and `code` here.\n\n- one\n- two"


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat()


def _record(at: float, role: str, content: object) -> str:
    return json.dumps({"timestamp": _iso(at), "type": role, "message": {"role": role, "content": content}}) + "\n"


def _turn_attrs(slug: str, activity: str, cost: float, tokens: int) -> dict:
    return {
        "workhorse.visit.slug": slug, "session.id": f"{SESSION}-{slug[:9]}", "work_id": "sign-in-with-a-code",
        "model": "claude-sonnet-5", "activity": activity, "usage.output_tokens": tokens,
        "usage.cache_read_input_tokens": 2_100_000, "total_cost_usd": cost, "backend": "claude",
    }


async def _no_volumes(_container_id: str) -> None:
    return None


@contextmanager
def _run(run: str, tmp: Path, *, native: bool = True, turns: bool = True, running: bool = False, hostile: bool = False, rich: bool = False, old: bool = False, long_live: bool = False) -> Iterator[str]:
    from groom import app as app_module
    from groom import state as groom_state
    from groom import store, turns as turn_archive
    from groom.models import WorkflowState

    container = f"{run}-box"[:12].ljust(12, "x")
    base = time.time() - 4000.0
    runs_dir = tmp / "runs" / run
    if turns:
        spans = [
            span("r1", "t1", "", "coder", "run:coder", base, 3900, {}, 1, run),
            span("f1", "t1", "r1", "qa", "qa", base + 1, 3800, {"workhorse.depth": 0}, 1, run),
            span("s1", "t1", "f1", "work", "work", base + 2, 3700, STATE, 1, run),
            span("n1", "t1", "s1", "document-story", "document-story", base + 3, 600, {"workhorse.depth": 2}, 1, run),
            span("a1", "t1", "n1", "document-story", "agent_turn", base + 10, 120, _turn_attrs(FIRST, "Documented the reset email flow.", 1.25, 3100), 1, run),
            span("n2", "t1", "s1", "qa-story", "qa-story", base + 700, 1500, {"workhorse.depth": 2}, 1, run),
            span("a2", "t1", "n2", "qa-story", "agent_turn", base + 710, 2460, _turn_attrs(SECOND, "Stack up on a free port. 7 of 9 pass", 6.12, 21400), 1, run),
        ]
        if old:
            for one in spans:
                one["attrs"].pop("workhorse.visit.slug", None)
        store.insert_spans(spans)
        archived = []
        second_text = HTML_TEXT + "\n\n" + MARKDOWN_IMAGE if hostile else RICH_TEXT if rich else "Port 5432 is held, so I will use a free port."
        for slug, seq, start, message in ((FIRST, 1, base + 10, "Documented the flow."), (SECOND, 2, base + 710, second_text)):
            if old and slug == SECOND:
                continue
            session = f"{SESSION}-{slug[:9]}"
            root = turn_archive.transcripts_root() / run / f"{slug}__{session}"
            root.mkdir(parents=True, exist_ok=True)
            tool = {"type": "tool_use", "id": "c1", "name": "Bash", "input": {"command": HTML_TEXT if hostile else "make up"}}
            (root / "transcript.jsonl").write_text(
                _record(start + 1, "assistant", message) + _record(start + 2, "assistant", [tool])
            )
            archived.append({
                "run_id": run, "node": slug.split("-", 2)[2], "session_id": session, "generation": 1, "seq": seq,
                "ts": start, "path": f"{run}/{slug}__{session}",
            })
        store.insert_turns(archived)
    if running:
        live = runs_dir / "transcripts" / "live"
        live.mkdir(parents=True, exist_ok=True)
        update = {"sessionUpdate": "agent_message_chunk", "content": {"type": "text", "text": "Rerunning the locked account scenario."}}
        lines = 230 if long_live else 1
        (live / f"{RUNNING}.jsonl").write_text("".join(json.dumps({
            "sessionId": SESSION, "update": update, "_meta": {"ts": time.time() - 30 + number * 0.01, "node": "qa-story"},
        }) + "\n" for number in range(lines)))
    patched = patch.object(app_module, "_ensure_volumes", _no_volumes)
    patched.start()
    groom_state.upsert_workflow(
        container, name=f"coder-{run}", workflow_type="coder", repo_name="acme", repo_branch="main",
        current_node="qa-story", activity="working", run_id=run, state=WorkflowState("running"), native=native,
        workspace_volume=str(tmp / "ws"), runs_volume=str(runs_dir),
    )
    try:
        yield run
    finally:
        groom_state.WORKFLOWS.pop(container, None)
        store.delete_run_telemetry(run)
        patched.stop()


def _pick(page, run: str) -> None:
    container = f"{run}-box"[:12].ljust(12, "x")
    page.locator(f'#runs-list .row[data-worker-id="{container}"]').click()
    page.wait_for_selector("#detail .dtabs", timeout=10000)


def _open_activity(page) -> None:
    page.get_by_role("tab", name="Activity").click()
    page.wait_for_selector("#detail-panel .feed, #detail-panel .empty-big, #detail-panel .side-state", timeout=10000)


def _rows(page):
    return page.locator("#detail-panel .tl button.ev")


def test_the_activity_tab_follows_overview_and_ends_the_tabs_of_a_run_without_a_checkout(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-tabs", tmp_path) as run:
        page = _open(live)
        try:
            _pick(page, run)
            names = [name.strip() for name in page.get_by_role("tab").all_inner_texts()]
            assert names == ["Overview", "Activity"], names
        finally:
            page.close()


def test_the_tab_lists_turns_oldest_first_each_with_time_node_duration_cost_and_result(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-list", tmp_path) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(_rows(page)).to_have_count(2)
            first, second = _rows(page).nth(0), _rows(page).nth(1)
            assert "document-story" in first.inner_text() and "qa-story" in second.inner_text()
            text = first.inner_text()
            assert re.search(r"\d\d:\d\d", text)
            assert "2m" in text and "$1.25" in text
            assert "Documented the reset email flow." in text
            assert "41m" in second.inner_text() and "$6.12" in second.inner_text()
        finally:
            page.close()


def test_selecting_a_row_opens_the_turn_beside_the_list_and_marks_it_selected(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-pane", tmp_path) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
            expect(_rows(page).nth(1)).to_have_attribute("aria-current", "true")
            _rows(page).nth(0).click()
            expect(page.locator(".rd .rd-head")).to_contain_text("document-story")
            expect(_rows(page).nth(0)).to_have_attribute("aria-current", "true")
            expect(_rows(page).nth(1)).not_to_have_attribute("aria-current", "true")
            tl, rd = page.locator(".tl").bounding_box(), page.locator(".rd").bounding_box()
            assert tl is not None and rd is not None
            assert tl["x"] < rd["x"] and abs(tl["y"] - rd["y"]) < 4
        finally:
            page.close()


def test_the_pane_head_names_node_work_item_pass_visit_model_duration_cost_and_output(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-head", tmp_path) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            page.wait_for_selector(".rd .rd-head")
            head = page.locator(".rd .rd-head").inner_text()
            for want in ("qa-story", "sign-in-with-a-code", "qa · 1st pass", "visit 001-00002", "claude-sonnet-5", "41m", "$6.12", "out 21.4k", "cache read 2.1M"):
                assert want in head, (want, head)
        finally:
            page.close()


def test_the_pane_shows_messages_as_prose_and_each_tool_call_as_one_line(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-body", tmp_path) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(".rd .at-msg .at-text")).to_have_text("Port 5432 is held, so I will use a free port.")
            tool = page.locator(".rd .at-tool")
            expect(tool).to_have_count(1)
            assert tool.inner_text().split() == ["Bash", "make", "up"]
        finally:
            page.close()


def test_a_running_turn_reads_running_in_its_row_and_pane_with_elapsed_time_and_no_cost_yet(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-live", tmp_path, running=True) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(_rows(page)).to_have_count(3)
            row = _rows(page).nth(2)
            assert ", running," in (row.get_attribute("aria-label") or "")
            assert re.search(r"\b\d+s\b", row.locator(".m").inner_text())
            expect(page.locator(".rd .rd-head")).to_contain_text("running")
            expect(page.locator(".rd .rd-head")).to_contain_text("lands at turn end")
            head = page.locator(".rd .rd-head").inner_text()
            assert "sign-in-with-a-code" not in head and "claude-sonnet" not in head and "pass" not in head, head
            expect(page.locator(".rd .at-text")).to_have_text("Rerunning the locked account scenario.")
        finally:
            page.close()


def test_a_container_runs_activity_tab_works_as_a_native_runs_does(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-box", tmp_path, native=False) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(_rows(page)).to_have_count(2)
            expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
            expect(page.locator(".rd .at-text")).to_have_text("Port 5432 is held, so I will use a free port.")
        finally:
            page.close()


def test_a_run_with_no_telemetry_says_so_in_its_activity_tab(tmp_path):
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-empty", tmp_path, turns=False) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            text = page.locator("#detail-panel .empty-big").inner_text()
            assert text == "No telemetry for this run. It was recorded before telemetry, or it exports to another collector."
            assert page.locator("#detail-panel .tl").count() == 0
            assert page.locator("#detail-panel .feedbar").count() == 0
        finally:
            page.close()


def test_a_run_with_telemetry_and_no_turn_says_it_has_no_activity_yet_and_that_it_is_alive(tmp_path):
    from groom import state
    from groom.models import RunTelemetry

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-quiet", tmp_path, turns=False) as run:
        now = time.time()
        state.RUNS[run] = RunTelemetry(
            run_id=run, workflow="coder", current_node="", node_elapsed_s=0.0, turn_active=False,
            last_heartbeat_ts=now, last_span_ts=now, first_seen_ts=now - 60, last_telemetry_ts=now,
        )
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            text = page.locator("#detail-panel").inner_text()
            assert "No activity yet" in text and "The run is alive" in text
            assert page.locator("#detail-panel .tl").count() == 0
        finally:
            page.close()
            state.RUNS.pop(run, None)


def test_a_turn_being_read_shows_a_reading_state_that_clears_when_it_appears(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-wait", tmp_path) as run:
        page = _open(live)
        held = []
        page.route(re.compile(r"/activity/\d"), lambda route: held.append(route))
        try:
            _pick(page, run)
            page.get_by_role("tab", name="Activity").click()
            reading = page.locator(".rd .detail-empty.loading")
            expect(reading).to_have_attribute("aria-busy", "true")
            expect(reading).to_contain_text("Reading this turn")
            expect(_rows(page)).to_have_count(2)
            page.wait_for_function("true")
            while not held:
                page.wait_for_timeout(50)
            held[0].continue_()
            expect(reading).to_have_count(0)
            expect(page.locator(".rd .rd-head")).to_be_visible()
        finally:
            page.close()


def test_a_turn_that_cannot_be_read_says_so_keeps_the_list_and_a_retry_clears_it(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-bad-turn", tmp_path) as run:
        page = _open(live)
        failing = {"on": True}

        def handle(route):
            if failing["on"]:
                route.fulfill(status=503, body="{}", content_type="application/json")
            else:
                route.continue_()

        page.route(re.compile(r"/activity/\d"), handle)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(".rd .side-state")).to_contain_text("This turn could not be read")
            expect(_rows(page)).to_have_count(2)
            failing["on"] = False
            page.get_by_role("button", name="Retry now").click()
            expect(page.locator(".rd .side-state")).to_have_count(0)
            expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
        finally:
            page.close()


def test_a_timeline_that_cannot_be_read_says_so_never_reads_as_empty_and_a_retry_clears_it(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-bad-list", tmp_path) as run:
        page = _open(live)
        failing = {"on": True}

        def handle(route):
            if failing["on"]:
                route.fulfill(status=500, body="{}", content_type="application/json")
            else:
                route.continue_()

        page.route(re.compile(r"/activity$"), handle)
        try:
            _pick(page, run)
            page.get_by_role("tab", name="Activity").click()
            alert = page.locator("#detail-panel .side-state")
            expect(alert).to_contain_text("activity could not be read")
            assert "No activity yet" not in page.locator("#detail-panel").inner_text()
            failing["on"] = False
            page.get_by_role("button", name="Retry now").click()
            expect(alert).to_have_count(0)
            expect(_rows(page)).to_have_count(2)
        finally:
            page.close()


def test_html_in_a_message_or_a_tool_line_renders_as_text_and_no_script_runs(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-xss", tmp_path, hostile=True) as run:
        page = _open(live)
        requested: list[str] = []
        page.on("request", lambda request: requested.append(request.url))
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(".rd .at-tool .at-tool-sum")).to_have_text(HTML_TEXT)
            expect(page.locator(".rd .at-msg .at-text")).to_contain_text(HTML_TEXT)
            expect(page.locator(".rd .at-msg .at-text")).to_contain_text("remote logo")
            page.wait_for_timeout(300)
            assert page.evaluate("window.__pwned") is None
            assert page.locator(".rd img, .rd script, .rd picture, .rd source").count() == 0
            assert not [url for url in requested if "pixel.png" in url]
        finally:
            page.close()


def test_the_other_tabs_behave_as_they_did(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-others", tmp_path) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            page.get_by_role("tab", name="Overview").click()
            expect(page.locator("#detail-panel .ov")).to_be_visible()
            assert page.get_by_role("tab", name="Overview").get_attribute("aria-selected") == "true"
        finally:
            page.close()


def test_the_tab_and_each_row_have_a_role_a_name_and_keyboard_operation_and_axe_is_clean(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-a11y", tmp_path, running=True) as run:
        page = _open(live)
        try:
            _pick(page, run)
            page.get_by_role("tab", name="Overview").focus()
            page.keyboard.press("ArrowRight")
            expect(page.get_by_role("tab", name="Activity")).to_have_attribute("aria-selected", "true")
            page.wait_for_selector("#detail-panel .feed")
            expect(page.get_by_role("log", name="Run activity")).to_be_visible()
            names = [row.get_attribute("aria-label") or "" for row in _rows(page).all()]
            assert all(names) and ", running," in names[-1] and ", finished," in names[0], names
            _rows(page).nth(0).focus()
            page.keyboard.press("Enter")
            expect(_rows(page).nth(0)).to_have_attribute("aria-current", "true")
            violations = _scan(page)
            assert violations == [], violations
        finally:
            page.close()


def test_a_message_written_in_markdown_reads_as_formatted_prose(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-md", tmp_path, rich=True) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            text = page.locator(".rd .at-msg .at-text")
            expect(text.locator("strong")).to_have_text("Bold claim")
            expect(text.locator("code")).to_have_text("code")
            expect(text.locator("li")).to_have_count(2)
        finally:
            page.close()


def test_a_turn_of_an_old_run_matches_its_one_archived_record_and_a_turn_with_none_says_so(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-old", tmp_path, old=True) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(_rows(page)).to_have_count(2)
            expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
            expect(page.locator(".rd .rd-head")).to_contain_text("$6.12")
            head = page.locator(".rd .rd-head").inner_text()
            assert "0th" not in head and "pass 0" not in head and "visit" not in head and "1st pass" in head, head
            expect(page.locator(".rd .at-note")).to_contain_text("No record of this turn")
            assert page.locator(".rd .at-msg").count() == 0
            assert page.locator(".rd .retry-turn, .rd button").count() == 0
            _rows(page).nth(0).click()
            expect(page.locator(".rd .at-msg .at-text")).to_have_text("Documented the flow.")
            assert page.locator(".rd .at-note", has_text="No record of this turn").count() == 0
        finally:
            page.close()


def test_a_finished_turn_whose_record_files_are_gone_says_no_record_not_an_empty_turn(tmp_path):
    import shutil

    from groom import turns as turn_archive
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-gone", tmp_path) as run:
        for root in (turn_archive.transcripts_root() / run).glob(f"{SECOND}__*"):
            shutil.rmtree(root)
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(_rows(page)).to_have_count(2)
            expect(page.locator(".rd .at-note")).to_contain_text("No record of this turn")
            body = page.locator(".rd .rd-body").inner_text()
            assert "recorded no messages" not in body and "did not record the prompt" not in body, body
        finally:
            page.close()


def test_a_running_turn_whose_start_the_live_history_dropped_says_earlier_output_is_not_shown(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("act-cut", tmp_path, running=True, long_live=True) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(".rd .at-note")).to_have_text("Earlier output of this turn is not shown.")
        finally:
            page.close()
    with _run("act-whole", tmp_path, running=True) as run:
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(page.locator(".rd .at-text")).to_have_text("Rerunning the locked account scenario.")
            assert page.locator(".rd .at-note").count() == 0
        finally:
            page.close()
