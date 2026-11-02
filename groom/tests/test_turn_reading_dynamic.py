from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_activity_tab_dynamic import (
    FIRST,
    HTML_TEXT,
    SECOND,
    SESSION,
    _open_activity,
    _pick,
    _record,
    _rows,
    _run,
)

PROMPT = "Bring the stack up on a free port, then run every scenario of the plan and report each result."
THINKING = "The default port is taken by another stack, so this one needs an offset."
FINAL = "7 of 9 scenarios pass. The spec does not say which status a locked account gets."
LONG_OUTPUT = "\n".join(f"scenario expired-code step {number} {'ok' if number % 3 else 'retrying'}" for number in range(1, 61)) + "\nE  expected 410, got 500"
SHORT_OUTPUT = "E  expected 423, got 401\nscenarios/locked_account.py:18"


def _call(at: float, name: str, args: dict, call_id: str) -> str:
    return _record(at, "assistant", [{"type": "tool_use", "id": call_id, "name": name, "input": args}])


def _answer(at: float, call_id: str, output: str, failed: bool = False) -> str:
    return _record(at, "user", [{"type": "tool_result", "tool_use_id": call_id, "content": output, "is_error": failed}])


def _first_stamp(root: Path) -> float:
    first = json.loads((root / "transcript.jsonl").read_text().splitlines()[0])
    return datetime.fromisoformat(first["timestamp"]).timestamp() - 1


def _write_turn(run: str, slug: str, build, prompt: str | None = PROMPT) -> None:
    from groom import turns as turn_archive

    root = turn_archive.transcripts_root() / run / f"{slug}__{SESSION}-{slug[:9]}"
    start = _first_stamp(root)
    (root / "transcript.jsonl").write_text("".join(build(start)))
    if prompt is not None:
        (root / "prompt.md").write_text(prompt)


def _long_turn(start: float, *, thinking: str | None = THINKING, text: str = "Port 5432 is held, so I will use a free port.", output: str = LONG_OUTPUT, final: str = FINAL) -> list[str]:
    opening: object = [{"type": "text", "text": text}]
    if thinking:
        opening = [{"type": "thinking", "thinking": thinking}, *opening]
    return [
        _record(start + 1, "assistant", opening),
        _call(start + 2, "Read", {"file_path": "plan.md"}, "r1"), _answer(start + 4, "r1", "plan"),
        _call(start + 5, "Read", {"file_path": "stack.yml"}, "r2"), _answer(start + 8, "r2", "stack"),
        _call(start + 9, "Grep", {"pattern": "port"}, "g1"), _answer(start + 10, "g1", "3 matches"),
        _call(start + 11, "Bash", {"command": "ostler stack up"}, "b1"), _answer(start + 15, "b1", "up"),
        _call(start + 16, "Bash", {"command": "run_qa_plan expired-code"}, "f1"), _answer(start + 40, "f1", output, True),
        _call(start + 41, "Edit", {"file_path": "plan.md"}, "e1"), _answer(start + 42, "e1", "edited"),
        _record(start + 50, "assistant", final),
    ]


def _enter(page, run: str) -> None:
    _pick(page, run)
    _open_activity(page)
    page.wait_for_selector(".rd .rd-body")


def _body(page):
    return page.locator(".rd .rd-body")


def _fold(page):
    return page.locator(".rd button.tool-run")


def test_the_prompt_starts_collapsed_and_is_labelled_with_its_size(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-prompt", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            prompt = page.locator(".rd details.prompt")
            expect(prompt).to_have_count(1)
            expect(prompt.locator("summary")).to_have_text("Prompt · 19 words")
            assert prompt.evaluate("el => el.open") is False
            expect(page.locator(".rd details.prompt .at-text")).to_have_count(0)
            assert PROMPT not in _body(page).inner_text()
        finally:
            page.close()


def test_opening_the_prompt_shows_it_and_closing_it_hides_it(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-prompt-open", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            summary = page.locator(".rd details.prompt summary")
            summary.click()
            expect(page.locator(".rd details.prompt .at-text")).to_have_text(PROMPT)
            summary.click()
            expect(page.locator(".rd details.prompt .at-text")).to_have_count(0)
            assert PROMPT not in _body(page).inner_text()
        finally:
            page.close()


def test_the_thinking_starts_collapsed(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-think", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            thinking = page.locator(".rd details.thought")
            expect(thinking).to_have_count(1)
            expect(thinking.locator("summary")).to_have_text("Thinking")
            assert thinking.evaluate("el => el.open") is False
            assert THINKING not in _body(page).inner_text()
        finally:
            page.close()


def test_opening_the_thinking_shows_it_and_closing_it_hides_it(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-think-open", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            summary = page.locator(".rd details.thought summary")
            summary.click()
            expect(page.locator(".rd details.thought .at-text")).to_have_text(THINKING)
            summary.click()
            expect(page.locator(".rd details.thought .at-text")).to_have_count(0)
            assert THINKING not in _body(page).inner_text()
        finally:
            page.close()


def test_a_run_of_successful_tool_calls_folds_to_one_line_counting_them_by_tool_with_their_time(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-fold", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            expect(_fold(page)).to_have_count(1)
            expect(_fold(page)).to_have_text("▸ 2 Read · 1 Grep · 1 Bash · 10s")
            expect(_fold(page)).to_have_attribute("aria-expanded", "false")
            sums = page.locator(".rd .at-tool .at-tool-sum").all_inner_texts()
            assert "stack.yml" not in sums and "ostler stack up" not in sums
        finally:
            page.close()


def test_opening_the_tool_line_shows_one_line_per_tool_call_and_closing_it_folds_them(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-fold-open", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            before = page.locator(".rd .at-tool").count()
            _fold(page).click()
            expect(_fold(page)).to_have_attribute("aria-expanded", "true")
            expect(page.locator(".rd .at-tool")).to_have_count(before + 4)
            lines = page.locator(".rd .at-tool .at-tool-head").all_inner_texts()
            for want in ("Read\nplan.md", "Read\nstack.yml", "Grep\nport", "Bash\nostler stack up"):
                assert any(line.replace("\n\n", "\n").startswith(want) for line in lines), (want, lines)
            _fold(page).click()
            expect(_fold(page)).to_have_attribute("aria-expanded", "false")
            expect(page.locator(".rd .at-tool")).to_have_count(before)
        finally:
            page.close()


def test_a_failed_tool_call_stands_outside_any_fold(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-outside", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            failed = page.locator(".rd .at-tool-head.failed")
            expect(failed).to_have_count(1)
            expect(failed).to_be_visible()
            expect(_fold(page)).to_have_attribute("aria-expanded", "false")
            assert "expired-code" not in _fold(page).inner_text()
            order = page.evaluate("""() => [...document.querySelectorAll('.rd .rd-body > *')].map((el) => el.className.split(' ')[0] + ':' + (el.querySelector('.at-tool-head.failed') ? 'failed' : ''))""")
            fold_at = next(at for at, item in enumerate(order) if item.startswith("tool-run"))
            failed_at = next(at for at, item in enumerate(order) if item.endswith(":failed"))
            assert fold_at < failed_at
        finally:
            page.close()


def test_a_failed_tool_call_is_marked_in_red_and_in_words_with_its_output_in_full(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-red", tmp_path) as run:
        _write_turn(run, SECOND, lambda start: _long_turn(start, output=SHORT_OUTPUT))
        page = _open(live)
        try:
            _enter(page, run)
            head = page.locator(".rd .at-tool-head.failed")
            expect(head.locator(".at-tool-state")).to_have_text("✕ failed")
            assert head.locator(".at-tool-name").evaluate("el => getComputedStyle(el).color") == "rgb(248, 113, 113)"
            assert head.locator(".at-tool-state").evaluate("el => getComputedStyle(el).color") == "rgb(248, 113, 113)"
            expect(page.locator(".rd pre.at-tool-body")).to_have_text(SHORT_OUTPUT)
            assert head.locator(".at-tool-time").inner_text() == "24s"
        finally:
            page.close()


def test_a_long_failed_output_scrolls_in_its_own_box_and_the_turn_around_it_stays_in_place(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-long", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            page.set_viewport_size({"width": 1400, "height": 1100})
            _enter(page, run)
            box = page.locator(".rd pre.at-tool-body")
            expect(box).to_have_text(LONG_OUTPUT)
            sizes = box.evaluate("el => [el.clientHeight, el.scrollHeight, getComputedStyle(el).overflowY]")
            assert sizes[0] <= 222 and sizes[1] > sizes[0] + 200 and sizes[2] in ("auto", "scroll"), sizes
            final = page.locator(".rd .at-msg.output")
            before = final.bounding_box()
            body_scroll = _body(page).evaluate("el => el.scrollTop")
            box.hover()
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(300)
            assert box.evaluate("el => el.scrollTop") > 0
            assert _body(page).evaluate("el => el.scrollTop") == body_scroll
            assert final.bounding_box() == before
        finally:
            page.close()


def test_the_final_output_is_set_apart_from_the_other_messages(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-final", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            output = page.locator(".rd .at-msg.output")
            expect(output).to_have_count(1)
            expect(output.locator(".at-role")).to_have_text("Output")
            expect(output.locator(".at-text")).to_have_text(FINAL)
            plain = page.locator(".rd .at-msg:not(.output):not(.prompt):not(.thought)")
            expect(plain).to_have_count(1)
            expect(plain.locator(".at-role")).to_have_text("assistant")
            assert output.evaluate("el => getComputedStyle(el).borderLeftColor") != plain.evaluate("el => getComputedStyle(el).borderLeftColor")
        finally:
            page.close()


def test_a_backend_that_recorded_no_prompt_or_thinking_says_so_where_they_would_sit(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-none", tmp_path) as run:
        _write_turn(run, SECOND, lambda start: _long_turn(start, thinking=None), prompt=None)
        page = _open(live)
        try:
            _enter(page, run)
            note = page.get_by_text("This backend did not record the prompt or the thinking for this turn.")
            expect(note).to_be_visible()
            expect(page.locator(".rd details.prompt, .rd details.thought")).to_have_count(0)
            first_message = page.locator(".rd .at-msg").first.bounding_box()
            where = note.bounding_box()
            assert where is not None and first_message is not None and where["y"] < first_message["y"]
        finally:
            page.close()


def test_a_turn_with_only_its_thinking_missing_names_just_the_thinking(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-half", tmp_path) as run:
        _write_turn(run, SECOND, lambda start: _long_turn(start, thinking=None))
        page = _open(live)
        try:
            _enter(page, run)
            expect(page.locator(".rd details.prompt")).to_have_count(1)
            expect(page.get_by_text("This backend did not record the thinking for this turn.")).to_be_visible()
        finally:
            page.close()


def test_selecting_another_turn_starts_it_collapsed_again(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-again", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        _write_turn(run, FIRST, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            page.locator(".rd details.prompt summary").click()
            page.locator(".rd details.thought summary").click()
            _fold(page).click()
            expect(page.locator(".rd details.prompt .at-text")).to_have_count(1)
            _rows(page).nth(0).click()
            expect(page.locator(".rd .rd-head")).to_contain_text("document-story")
            assert page.locator(".rd details.prompt").evaluate("el => el.open") is False
            _rows(page).nth(1).click()
            expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
            assert page.locator(".rd details.prompt").evaluate("el => el.open") is False
            assert page.locator(".rd details.thought").evaluate("el => el.open") is False
            expect(_fold(page)).to_have_attribute("aria-expanded", "false")
            expect(page.locator(".rd details .at-text")).to_have_count(0)
        finally:
            page.close()


def test_prompt_thinking_and_tool_output_render_as_text_and_no_script_runs(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-xss", tmp_path) as run:
        _write_turn(
            run, SECOND,
            lambda start: _long_turn(start, thinking=HTML_TEXT + "\n\n![remote logo](http://127.0.0.1:9/pixel.png)", output=HTML_TEXT),
            prompt=HTML_TEXT + "\n\n![remote logo](http://127.0.0.1:9/pixel.png)",
        )
        page = _open(live)
        requested: list[str] = []
        page.on("request", lambda request: requested.append(request.url))
        try:
            _enter(page, run)
            page.locator(".rd details.prompt summary").click()
            page.locator(".rd details.thought summary").click()
            expect(page.locator(".rd details.prompt .at-text")).to_contain_text(HTML_TEXT)
            expect(page.locator(".rd details.prompt .at-text")).to_contain_text("remote logo")
            expect(page.locator(".rd details.thought .at-text")).to_contain_text(HTML_TEXT)
            expect(page.locator(".rd pre.at-tool-body")).to_have_text(HTML_TEXT)
            page.wait_for_timeout(300)
            assert page.evaluate("window.__pwned") is None
            assert page.locator(".rd img, .rd script, .rd picture, .rd source").count() == 0
            assert not [url for url in requested if "pixel.png" in url]
        finally:
            page.close()


def _ax(page, name: str) -> dict:
    client = page.context.new_cdp_session(page)
    try:
        nodes = client.send("Accessibility.getFullAXTree")["nodes"]
    finally:
        client.detach()
    found = [node for node in nodes if (node.get("name") or {}).get("value", "").strip().lower() == name.lower() and not node.get("ignored")]
    assert found, (name, [(node.get("role", {}).get("value"), node.get("name", {}).get("value")) for node in nodes][:60])
    node = found[0]
    return {"role": node["role"]["value"], **{prop["name"]: prop["value"]["value"] for prop in node.get("properties", [])}}


def test_each_collapsible_part_has_a_role_a_name_keyboard_operation_and_its_open_state_is_exposed(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("rd-a11y", tmp_path) as run:
        _write_turn(run, SECOND, _long_turn)
        page = _open(live)
        try:
            _enter(page, run)
            parts = {
                "Prompt · 19 words": page.locator(".rd details.prompt summary"),
                "Thinking": page.locator(".rd details.thought summary"),
                "2 Read · 1 Grep · 1 Bash · 10s": _fold(page),
            }
            for name, control in parts.items():
                state = _ax(page, name)
                assert state["role"] in ("DisclosureTriangle", "button"), (name, state)
                assert state.get("expanded") is False, (name, state)
                control.focus()
                page.keyboard.press("Enter")
                opened = _ax(page, name)
                assert opened.get("expanded") is True, (name, opened)
                page.keyboard.press("Space")
                closed = _ax(page, name)
                assert closed.get("expanded") is False, (name, closed)
            expect(page.locator(".rd details .at-text")).to_have_count(0)
            for control in parts.values():
                control.click()
            violations = _scan(page)
            assert violations == [], violations
        finally:
            page.close()
