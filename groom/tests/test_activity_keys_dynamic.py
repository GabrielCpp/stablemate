"""Moving through the Activity timeline from the keyboard, and searching it, measured on the page the operator gets."""
from __future__ import annotations

from pathlib import Path

from test_activity_groups_dynamic import _open_all
from test_activity_follow_dynamic import CONTROL, LIST, _following, _in_view, _wheel_up
from test_activity_step_gate_dynamic import _stepped
from test_activity_tab_dynamic import _open_activity, _pick, _rows, _run
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)

SEARCH = '#detail-panel .feedbar input[aria-label="Search activity"]'
SELECTOR = '#detail-panel .feedbar select[aria-label="Work item"]'
SELECTED = "#detail-panel .tl button.ev[aria-current=true]"
STATUS = "#detail-panel [role=status]"


def _turns_page(tmp_path: Path, run: str):
    live = _live()
    assert live is not None, _UNAVAILABLE
    context = _run(run, tmp_path)
    name = context.__enter__()
    page = _open(live)
    _pick(page, name)
    _open_activity(page)
    return page, context


def _stepped_page(tmp_path: Path, run: str, **given):
    live = _live()
    assert live is not None, _UNAVAILABLE
    context = _stepped(run, tmp_path, **given)
    name = context.__enter__()
    page = _open(live)
    _pick(page, name)
    _open_activity(page)
    return page, context


def _selected_key(page) -> str:
    one = page.locator(SELECTED)
    return (one.get_attribute("data-slug") or one.get_attribute("data-entry") or "") if one.count() else ""


def _leave(page, context) -> None:
    page.close()
    context.__exit__(None, None, None)


def test_the_bar_labels_j_and_k_as_move_and_e_as_next_problem(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-bar")
    try:
        hints = page.locator("#detail-panel .feedbar .hint")
        expect(hints).to_have_count(2)
        expect(hints.nth(0)).to_have_text("j k move")
        expect(hints.nth(1)).to_have_text("e next problem")
        expect(page.locator(SEARCH)).to_have_attribute("placeholder", "Search rows and transcripts…")
    finally:
        _leave(page, context)


def test_j_selects_the_next_row_and_k_the_previous_one_and_the_pane_follows(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-move")
    try:
        first, second = _rows(page).nth(0), _rows(page).nth(1)
        first.click()
        expect(first).to_have_attribute("aria-current", "true")
        page.keyboard.press("j")
        expect(second).to_have_attribute("aria-current", "true")
        expect(page.locator("#detail-panel .rd-head")).to_contain_text("qa-story")
        page.keyboard.press("k")
        expect(first).to_have_attribute("aria-current", "true")
        expect(page.locator("#detail-panel .rd-head")).to_contain_text("document-story")
    finally:
        _leave(page, context)


def test_the_selected_row_stays_in_view_as_j_walks_down_a_long_timeline(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "key-view", filler=30, height=520) as (_l, page, _name):
        _wheel_up(page, 6000)
        expect(page.locator(CONTROL)).to_have_text("Paused")
        _rows(page).first.click()
        for _step in range(12):
            page.keyboard.press("j")
        expect(page.locator(SELECTED)).to_have_count(1)
        assert _in_view(page, page.locator(SELECTED))
        down = _selected_key(page)
        for _step in range(12):
            page.keyboard.press("k")
        assert _in_view(page, page.locator(SELECTED))
        assert _selected_key(page) != down


def test_on_another_tab_j_and_k_keep_moving_the_run_list(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("key-tab-a", tmp_path / "a") as first, _run("key-tab-b", tmp_path / "b") as second:
        page = _open(live)
        try:
            _pick(page, first)
            before = page.locator("#runs-list .row.selected").get_attribute("data-worker-id")
            page.keyboard.press("j")
            page.keyboard.press("k")
            page.keyboard.press("j")
            after = page.locator("#runs-list .row.selected").get_attribute("data-worker-id")
            expect(page.locator("#runs-list .row.selected")).to_have_count(1)
            assert before != after
            page.get_by_role("tab", name="Details").click()
            page.keyboard.press("k")
            assert page.locator("#runs-list .row.selected").get_attribute("data-worker-id") != after
            assert second
        finally:
            page.close()


def test_e_selects_the_next_problem_after_the_selection_and_wraps_to_the_first(tmp_path):
    page, context = _stepped_page(tmp_path, "key-next")
    try:
        _open_all(page)
        problems = page.locator("#detail-panel .tl button.ev[data-kind=failed], #detail-panel .tl button.ev[data-kind=retry], #detail-panel .tl button.ev[data-kind=churn]")
        keys = [problems.nth(number).get_attribute("data-entry") for number in range(problems.count())]
        assert len(keys) >= 3
        problems.first.click()
        seen = []
        for _step in range(len(keys)):
            page.keyboard.press("e")
            page.wait_for_function("(old) => document.querySelector('#detail-panel .tl button.ev[aria-current=true]').dataset.entry !== old", arg=seen[-1] if seen else keys[0])
            seen.append(_selected_key(page))
        assert seen == keys[1:] + keys[:1]
    finally:
        _leave(page, context)


def test_after_a_key_moves_the_selection_focus_sits_on_the_selected_row_and_enter_and_space_act_on_it(tmp_path):
    page, context = _stepped_page(tmp_path, "key-focus")
    try:
        _open_all(page)
        fold = page.locator("#detail-panel .tl button.ev.steps").first
        fold.click()
        opened = fold.get_attribute("aria-expanded")
        for key in ["e", "j", "k", "e"]:
            page.keyboard.press(key)
            page.wait_for_timeout(150)
            focused = page.evaluate("() => { const one = document.activeElement; return one ? (one.dataset.slug || one.dataset.entry || one.dataset.fold || '') : ''; }")
            assert focused == _selected_key(page), key
            assert page.locator("#detail-panel .tl :focus-visible").count() <= 1
        page.keyboard.press("e")
        page.wait_for_timeout(150)
        chosen = _selected_key(page)
        page.keyboard.press("Enter")
        page.keyboard.press("Space")
        page.wait_for_timeout(150)
        assert _selected_key(page) == chosen
        assert fold.get_attribute("aria-expanded") == opened
    finally:
        _leave(page, context)


def test_the_work_item_selector_keeps_one_width_whatever_its_options(tmp_path):
    page, context = _stepped_page(tmp_path, "key-width")
    try:
        wide = page.locator(SELECTOR).evaluate("one => one.getBoundingClientRect().width")
        page.locator(SELECTOR).evaluate("one => { one.options[1].text = 'x'.repeat(120); }")
        longer = page.locator(SELECTOR).evaluate("one => one.getBoundingClientRect().width")
        page.locator(SELECTOR).evaluate("one => { one.options[0].text = 'a'; for (const option of Array.from(one.options).slice(1)) option.remove(); }")
        shorter = page.locator(SELECTOR).evaluate("one => one.getBoundingClientRect().width")
        assert wide == longer == shorter == 155
    finally:
        _leave(page, context)


def test_with_no_problems_e_says_so_and_the_selection_stays(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-none")
    try:
        _rows(page).first.click()
        before = _selected_key(page)
        page.keyboard.press("e")
        expect(page.locator(STATUS).filter(has_text="This run has no problems.")).to_be_visible()
        assert _selected_key(page) == before
        page.keyboard.press("j")
        expect(page.locator(STATUS).filter(has_text="This run has no problems.")).to_have_count(0)
    finally:
        _leave(page, context)


def test_e_opens_a_folded_heading_to_reach_a_problem_inside_it(tmp_path):
    from playwright.sync_api import expect

    page, context = _stepped_page(tmp_path, "key-fold")
    try:
        heads = page.locator("#detail-panel .tl button.tl-group")
        for number in range(heads.count()):
            if heads.nth(number).get_attribute("aria-expanded") == "true":
                heads.nth(number).click()
        expect(page.locator("#detail-panel .tl button.ev[data-kind=failed]")).to_have_count(0)
        page.locator("body").click(position={"x": 5, "y": 5})
        page.keyboard.press("e")
        expect(page.locator(SELECTED)).to_have_count(1)
        assert _selected_key(page) != ""
        expect(page.locator(SELECTED)).to_be_visible()
        assert page.locator("#detail-panel .tl button.tl-group[aria-expanded=true]").count() >= 1
    finally:
        _leave(page, context)


def test_typing_in_the_search_field_narrows_the_timeline_at_once_and_highlights_the_match(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-narrow")
    try:
        expect(_rows(page)).to_have_count(2)
        page.locator(SEARCH).fill("Documented")
        expect(_rows(page)).to_have_count(1)
        expect(_rows(page).first.locator("mark")).to_have_text("Documented")
        page.locator(SEARCH).fill("")
        expect(_rows(page)).to_have_count(2)
    finally:
        _leave(page, context)


def test_search_reads_the_transcripts_of_this_run_and_a_found_row_says_in_transcript_with_the_line(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-transcript")
    try:
        page.locator(SEARCH).fill("5432")
        expect(_rows(page)).to_have_count(1)
        hit = _rows(page).first.locator(".hit")
        expect(hit).to_contain_text("in transcript:")
        expect(hit).to_contain_text("Port 5432 is held")
        expect(hit.locator("mark")).to_have_text("5432")
        expect(_rows(page).first.locator(".w")).to_have_count(1)
    finally:
        _leave(page, context)


def test_while_transcripts_are_searched_a_status_says_so_and_it_clears_when_the_search_ends(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-status")
    try:
        held = []
        page.route("**/api/run/*/search*", lambda route: held.append(route))
        page.locator(SEARCH).fill("5432")
        expect(page.locator(STATUS).filter(has_text="Searching the transcripts of this run…")).to_be_visible()
        for _wait in range(50):
            if held:
                break
            page.wait_for_timeout(100)
        held[0].continue_()
        expect(page.locator(STATUS).filter(has_text="Searching the transcripts")).to_have_count(0)
    finally:
        _leave(page, context)


def test_a_search_with_nothing_found_says_what_was_searched_and_offers_to_clear_it(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-nothing")
    try:
        page.locator(SEARCH).fill("pgbouncer")
        message = page.locator("#detail-panel .tl .detail-empty")
        expect(message).to_contain_text("Nothing in this run matches “pgbouncer”.")
        expect(page.locator("#detail-panel .rd .detail-empty")).to_have_text("Select a row to read it.")
        message.get_by_role("button", name="Clear the search").click()
        expect(page.locator(SEARCH)).to_have_value("")
        expect(_rows(page)).to_have_count(2)
    finally:
        _leave(page, context)


def test_a_failed_transcript_search_says_so_and_offers_a_retry_and_the_row_matches_stay(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-retry")
    try:
        page.route("**/api/run/*/search*", lambda route: route.fulfill(status=503, body="{}"))
        page.locator(SEARCH).fill("free port")
        note = page.locator(STATUS).filter(has_text="could not be searched")
        expect(note).to_contain_text("These rows match the row text only.")
        expect(_rows(page)).to_have_count(1)
        page.unroute("**/api/run/*/search*")
        note.get_by_role("button", name="Retry now").click()
        expect(page.locator(STATUS).filter(has_text="could not be searched")).to_have_count(0)
        expect(_rows(page)).to_have_count(1)
        page.locator(SEARCH).fill("5432")
        expect(_rows(page).first.locator(".hit")).to_contain_text("in transcript:")
    finally:
        _leave(page, context)


def test_a_successful_retry_adds_the_transcript_matches(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-retry-ok")
    try:
        page.route("**/api/run/*/search*", lambda route: route.fulfill(status=503, body="{}"))
        page.locator(SEARCH).fill("5432")
        note = page.locator(STATUS).filter(has_text="could not be searched")
        expect(note).to_be_visible()
        expect(_rows(page)).to_have_count(0)
        page.unroute("**/api/run/*/search*")
        note.get_by_role("button", name="Retry now").click()
        expect(_rows(page)).to_have_count(1)
        expect(_rows(page).first.locator(".hit")).to_contain_text("Port 5432 is held")
        expect(page.locator(STATUS).filter(has_text="could not be searched")).to_have_count(0)
    finally:
        _leave(page, context)


def test_search_matches_rows_inside_folded_headings_and_shows_them(tmp_path):
    from playwright.sync_api import expect

    page, context = _stepped_page(tmp_path, "key-search-fold")
    try:
        heads = page.locator("#detail-panel .tl button.tl-group")
        for number in range(heads.count()):
            if heads.nth(number).get_attribute("aria-expanded") == "true":
                heads.nth(number).click()
        expect(page.locator("#detail-panel .tl button.ev")).to_have_count(0)
        page.locator(SEARCH).fill("ensure_stack")
        expect(page.locator("#detail-panel .tl button.ev")).to_have_count(1)
        expect(page.locator("#detail-panel .tl button.ev mark")).to_have_text("ensure_stack")
    finally:
        _leave(page, context)


def test_the_work_item_selector_limits_the_timeline_to_one_item_and_its_first_option_shows_every_item(tmp_path):
    from playwright.sync_api import expect

    page, context = _stepped_page(tmp_path, "key-item")
    try:
        options = page.locator(SELECTOR + " option")
        assert options.nth(0).inner_text() == "All work items"
        assert options.count() >= 3
        _open_all(page)
        total = _rows(page).count()
        page.locator(SELECTOR).select_option(label="reset")
        assert _rows(page).count() < total
        expect(page.locator("#detail-panel .tl .tl-group")).to_have_count(1)
        assert "reset" in page.locator("#detail-panel .tl .tl-group").inner_text()
        page.locator(SELECTOR).select_option(index=0)
        expect(page.locator("#detail-panel .tl .tl-group")).to_have_count(2)
        expect(_rows(page)).to_have_count(total)
    finally:
        _leave(page, context)


def test_search_and_the_selector_apply_together_and_clearing_them_restores_the_timeline(tmp_path):
    from playwright.sync_api import expect

    page, context = _stepped_page(tmp_path, "key-both")
    try:
        before = page.locator("#detail-panel .tl .tl-group").count()
        page.locator(SELECTOR).select_option(label="sign-in")
        page.locator(SEARCH).fill("lint")
        expect(page.locator("#detail-panel .tl .tl-group")).to_have_count(1)
        page.locator(SELECTOR).select_option(label="reset")
        page.locator(SEARCH).fill("ensure_stack")
        expect(page.locator("#detail-panel .tl .detail-empty")).to_contain_text("Nothing in this run matches")
        page.locator(SEARCH).fill("")
        page.locator(SELECTOR).select_option(index=0)
        expect(page.locator("#detail-panel .tl .tl-group")).to_have_count(before)
    finally:
        _leave(page, context)


def test_j_k_and_e_typed_in_the_search_field_or_the_gate_answer_box_are_typed_as_text_and_move_nothing(tmp_path):
    from playwright.sync_api import expect

    page, context = _stepped_page(tmp_path, "key-typing", gate="open")
    try:
        _rows(page).first.click()
        before = _selected_key(page)
        page.locator(SEARCH).click()
        page.keyboard.type("jke")
        expect(page.locator(SEARCH)).to_have_value("jke")
        page.locator(SEARCH).fill("")
        assert _selected_key(page) == before
        _rows(page).first.click()
        before = _selected_key(page)
        page.locator("form[data-answer] textarea").click()
        page.keyboard.type("jke")

        expect(page.locator("form[data-answer] textarea")).to_have_value("jke")
        assert _selected_key(page) == before
    finally:
        _leave(page, context)


def test_with_the_work_item_selector_focused_j_k_and_e_move_nothing_in_the_timeline(tmp_path):
    page, context = _stepped_page(tmp_path, "key-select")
    try:
        _rows(page).first.click()
        before = _selected_key(page)
        page.locator(SELECTOR).focus()
        for key in ("j", "k", "e"):
            page.keyboard.press(key)
        assert _selected_key(page) == before
    finally:
        _leave(page, context)


def test_search_text_renders_as_harmless_text(tmp_path):
    from playwright.sync_api import expect

    page, context = _turns_page(tmp_path, "key-harmless")
    try:
        page.locator(SEARCH).fill("<img src=x onerror=window.__hit=1>")
        expect(page.locator("#detail-panel .tl .detail-empty")).to_contain_text("<img src=x onerror=window.__hit=1>")
        assert page.evaluate("() => window.__hit === undefined")
        assert page.locator("#detail-panel .tl img").count() == 0
    finally:
        _leave(page, context)


def test_the_search_field_and_selector_have_accessible_names_and_the_new_surface_has_no_axe_violations(tmp_path):
    page, context = _turns_page(tmp_path, "key-axe")
    try:
        assert page.get_by_role("searchbox", name="Search activity").count() == 1
        assert page.get_by_role("combobox", name="Work item").count() == 1
        page.locator(SEARCH).fill("5432")
        page.locator(f"{LIST} .hit").first.wait_for()
        assert _scan(page) == []
    finally:
        _leave(page, context)


def test_a_key_that_moves_to_a_row_out_of_view_pauses_following_and_a_key_in_view_keeps_it(tmp_path):
    from playwright.sync_api import expect

    with _following(tmp_path, "key-follow", filler=30, height=520) as (_l, page, _name):
        expect(page.locator(CONTROL)).to_have_text("Following")
        _rows(page).nth(_rows(page).count() - 3).click()
        page.keyboard.press("j")
        expect(page.locator(CONTROL)).to_have_text("Following")
        for _step in range(14):
            page.keyboard.press("k")
        expect(page.locator(CONTROL)).to_have_text("Paused")
        assert _in_view(page, page.locator(SELECTED))
        assert page.locator(LIST).evaluate("el => el.scrollHeight - el.clientHeight - el.scrollTop") > 4
