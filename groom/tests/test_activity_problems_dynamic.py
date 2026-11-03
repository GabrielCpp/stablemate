from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from test_activity_follow_dynamic import _IDS, _open_watched, _send
from test_activity_groups import BASE, _attrs, _polls
from test_activity_groups_dynamic import _open_all
from test_activity_keys_dynamic import SEARCH, SELECTED, SELECTOR, STATUS
from test_activity_step_gate_dynamic import _stepped
from test_activity_tab_dynamic import _open_activity, _pick, _rows, _run
from test_run_clock import span
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)

CHIP = '#detail-panel .feedbar button[data-filter="problems"].fchip'
LIST = "#detail-panel .tl"
BADGE = "#detail-activity-count"
TILE = "#detail-problems-link"
EXPECTED = 5
BROKEN = "001-00009-qa-story"


@contextmanager
def _problem_run(run: str, tmp: Path, *, answered: bool = True, broken: bool = False):
    from groom import store

    with _stepped(run, tmp, gate="answered" if answered else "") as name:
        _polls(5, name)
        if broken:
            store.insert_spans([span("ft", "t1", "sa", "qa-story", "agent_turn", BASE + 300, 20, _attrs("sign-in", **{"workhorse.visit.slug": BROKEN}), 1, name) | {"status": "ERROR"}])
        yield name


def _page(tmp_path: Path, run: str, *, activity: bool = True, watched: bool = False, broken: bool = False):
    live = _live()
    assert live is not None, _UNAVAILABLE
    context = _problem_run(run, tmp_path, broken=broken)
    name = context.__enter__()
    page = _open_watched(live) if watched else _open(live)
    _pick(page, name)
    if activity:
        _open_activity(page)
    return live, page, context, name


def _leave(page, context) -> None:
    page.close()
    context.__exit__(None, None, None)


def _on(page) -> None:
    page.locator(CHIP).click()
    page.wait_for_selector(f'{CHIP}[aria-pressed="true"]', timeout=5000)


def _keys(page) -> list[str]:
    return page.locator("#detail-panel .tl button.ev[data-entry]").evaluate_all("(rows) => rows.map((r) => r.dataset.entry)")


def _width(page) -> float:
    box = page.locator(LIST).bounding_box()
    assert box is not None
    return box["width"]


def _count_of(page) -> int:
    return int(page.locator(CHIP + " b").inner_text())


def test_the_bar_has_a_problems_control_with_the_count(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-chip")
    try:
        chip = page.locator(CHIP)
        expect(chip).to_have_count(1)
        expect(chip).to_have_text(f"Problems {EXPECTED}")
        expect(chip).to_have_attribute("aria-pressed", "false")
    finally:
        _leave(page, context)


def test_pressing_problems_narrows_the_timeline_to_its_problem_rows_under_their_headings_and_pressing_again_restores_it(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-narrow")
    try:
        whole = page.locator("#detail-panel .tl button.ev").count()
        _on(page)
        kinds = page.locator("#detail-panel .tl button.ev").evaluate_all("(rows) => rows.map((r) => r.dataset.kind || (r.dataset.fold ? 'steps' : 'turn'))")
        assert sorted(set(kinds)) == ["churn", "failed", "retry"], kinds
        assert page.locator("#detail-panel .tl button.tl-group").count() >= 1
        assert page.locator("#detail-panel .tl button.tl-flow").count() >= 1
        page.locator(CHIP).click()
        expect(page.locator(CHIP)).to_have_attribute("aria-pressed", "false")
        expect(page.locator("#detail-panel .tl button.ev")).to_have_count(whole)
    finally:
        _leave(page, context)


def test_the_problems_view_opens_at_its_newest_row(tmp_path):
    _live_, page, context, _name = _page(tmp_path, "prb-newest")
    try:
        _on(page)
        last = page.locator("#detail-panel .tl button.ev").last
        page.wait_for_function(
            "(list) => { const a = document.querySelector(list); return a.scrollHeight - a.clientHeight - a.scrollTop < 2; }",
            arg=LIST,
        )
        assert last.is_visible()
    finally:
        _leave(page, context)


def test_the_number_of_rows_in_the_problems_view_equals_its_count(tmp_path):
    _live_, page, context, _name = _page(tmp_path, "prb-rows")
    try:
        _on(page)
        assert len(_keys(page)) == _count_of(page) == EXPECTED
    finally:
        _leave(page, context)


def test_an_answered_gate_is_not_in_the_problems_view_and_adds_nothing_to_the_count(tmp_path):
    _live_, page, context, _name = _page(tmp_path, "prb-answered")
    try:
        _open_all(page)
        assert page.locator("#detail-panel .tl button.ev[data-kind=gate]").count() >= 1
        _on(page)
        assert page.locator("#detail-panel .tl button.ev[data-kind=gate]").count() == 0
        assert _count_of(page) == EXPECTED
    finally:
        _leave(page, context)


def test_the_activity_tab_shows_a_badge_with_the_count_that_equals_the_overview_attention_tile_and_says_it_in_words(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-badge", activity=False)
    try:
        tile = page.locator(TILE)
        expect(tile).to_have_text(f"{EXPECTED} problems")
        tab = page.get_by_role("tab", name=f"Activity, {EXPECTED} problems")
        expect(tab).to_have_count(1)
        expect(page.locator(BADGE)).to_have_text(f"{EXPECTED} problems")
        _open_activity(page)
        expect(page.locator(BADGE)).to_have_text(f"{EXPECTED} problems")
        assert _count_of(page) == EXPECTED
    finally:
        _leave(page, context)


def test_the_problem_count_on_the_attention_tile_opens_the_activity_tab_with_problems_on(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-tile", activity=False)
    try:
        page.locator(TILE).click()
        expect(page.get_by_role("tab", name="Activity", exact=False)).to_have_attribute("aria-selected", "true")
        expect(page.locator(f'{CHIP}[aria-pressed="true"]')).to_have_count(1)
        expect(page.locator("#detail-panel .tl button.ev")).to_have_count(EXPECTED)
    finally:
        _leave(page, context)


def test_selecting_a_backend_retry_says_what_happened_and_links_to_its_turn(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-retry")
    try:
        _on(page)
        page.locator("#detail-panel .tl button.ev[data-kind=retry]").click()
        body = page.locator(".rd .rd-body")
        expect(body).to_contain_text("The backend started the qa-story turn again after the attempt before it ended. It waited 30s first.")
        link = body.get_by_role("button", name="Open that turn")
        expect(link).to_have_count(1)
        link.click()
        expect(page.locator(".rd")).to_contain_text("visit 001-00002")
        expect(page.locator(SELECTED)).to_have_count(0)
    finally:
        _leave(page, context)


def test_selecting_a_churn_alert_says_what_repeated_and_what_came_next(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-churn")
    try:
        _on(page)
        page.locator("#detail-panel .tl button.ev[data-kind=churn]").click()
        body = page.locator(".rd .rd-body")
        expect(body).to_contain_text("poll has run 5 times in a row on reset with the same labels.")
        expect(body).to_contain_text("Nothing came after this.")
    finally:
        _leave(page, context)


@contextmanager
def _quiet(run: str, tmp: Path):
    with _run(run, tmp) as name:
        yield name


def test_a_run_with_no_problems_says_so_offers_the_whole_timeline_and_shows_no_badge(tmp_path):
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _quiet("prb-none", tmp_path) as name:
        page = _open(live)
        try:
            _pick(page, name)
            expect(page.locator(BADGE)).to_have_count(0)
            _open_activity(page)
            expect(page.locator(BADGE)).to_have_count(0)
            expect(page.locator(CHIP)).to_have_text("Problems 0")
            _on(page)
            expect(page.locator(STATUS).filter(has_text="This run has no problems.")).to_be_visible()
            page.get_by_role("button", name="Show the whole timeline").click()
            expect(page.locator(CHIP)).to_have_attribute("aria-pressed", "false")
            assert _rows(page).count() > 0
        finally:
            page.close()


def test_while_paused_in_the_problems_view_the_pill_counts_new_problems_and_names_them_as_problems(tmp_path):
    from playwright.sync_api import expect

    live, page, context, name = _page(tmp_path, "prb-pill", watched=True)
    try:
        _on(page)
        page.locator("#detail-panel .feedbar .follow").click()
        pill = page.locator("#detail-panel .newpill button")
        _send(live, name, node="late")
        page.wait_for_timeout(500)
        expect(pill).to_have_count(0)
        _send_failed(live, name)
        _send_failed(live, name)
        expect(pill).to_contain_text("new problem")
        expect(pill).to_contain_text("2 new problems")
    finally:
        _leave(page, context)


def _send_failed(live, run: str) -> None:
    import time
    import urllib.request

    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest
    from opentelemetry.proto.trace.v1.trace_pb2 import Status

    request = ExportTraceServiceRequest()
    resource_spans = request.resource_spans.add()
    for key, value in {"run_id": run, "workflow": "coder"}.items():
        kv = resource_spans.resource.attributes.add()
        kv.key, kv.value.string_value = key, value
    one = resource_spans.scope_spans.add().spans.add()
    one.trace_id = bytes.fromhex("ab" * 16)
    one.span_id = bytes.fromhex(f"{next(_IDS):016x}")
    one.name = "lint"
    now = time.time()
    one.start_time_unix_nano = int((now - 2) * 1e9)
    one.end_time_unix_nano = int(now * 1e9)
    one.status.code = Status.STATUS_CODE_ERROR
    kv = one.attributes.add()
    kv.key, kv.value.string_value = "workhorse.node", "lint"
    http = urllib.request.Request(live.url() + "v1/traces", data=request.SerializeToString(), headers={"Content-Type": "application/x-protobuf"})
    with urllib.request.urlopen(http, timeout=10) as reply:
        assert reply.status == 200


def test_e_steps_through_the_same_rows_the_problems_view_lists(tmp_path):
    _live_, page, context, _name = _page(tmp_path, "prb-e")
    try:
        _on(page)
        keys = _keys(page)
        page.locator("#detail-panel .tl button.ev").first.click()
        seen = [keys[0]]
        for _step in range(len(keys) - 1):
            page.keyboard.press("e")
            page.wait_for_function("(old) => document.querySelector('#detail-panel .tl button.ev[aria-current=true]').dataset.entry !== old", arg=seen[-1])
            seen.append(page.locator(SELECTED).get_attribute("data-entry") or "")
        assert seen == keys
    finally:
        _leave(page, context)


def test_search_and_the_work_item_filter_also_apply_inside_the_problems_view(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-filters")
    try:
        _on(page)
        before = len(_keys(page))
        page.locator(SELECTOR).select_option(label="reset")
        narrowed = len(_keys(page))
        assert 0 < narrowed < before
        page.locator(SELECTOR).select_option(index=0)
        page.locator(SEARCH).fill("churn")
        expect(page.locator("#detail-panel .tl button.ev[data-kind=churn]")).to_have_count(1)
        assert len(_keys(page)) == 1
    finally:
        _leave(page, context)


def test_the_control_exposes_its_pressed_state_an_accessible_name_and_keyboard_operation_and_the_view_passes_an_axe_scan(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-a11y")
    try:
        chip = page.get_by_role("button", name="Problems 5", exact=False)
        expect(chip).to_have_count(1)
        chip.focus()
        page.keyboard.press("Enter")
        expect(page.locator(CHIP)).to_have_attribute("aria-pressed", "true")
        page.keyboard.press("Space")
        expect(page.locator(CHIP)).to_have_attribute("aria-pressed", "false")
        page.keyboard.press("Space")
        expect(page.locator(CHIP)).to_have_attribute("aria-pressed", "true")
        violations = _scan(page)
        assert violations == [], violations
    finally:
        _leave(page, context)


def test_the_list_keeps_its_width_between_the_whole_timeline_and_the_problems_view(tmp_path):
    _live_, page, context, _name = _page(tmp_path, "prb-width")
    try:
        before = _width(page)
        _on(page)
        after = _width(page)
        assert abs(before - after) < 1
    finally:
        _leave(page, context)


def _newest_problem(page, run: str, *, only: str = "") -> str:
    return page.evaluate(
        """async ([id, only]) => {
          const data = await (await fetch('/api/run/' + id + '/activity')).json();
          let best = ['', -1];
          for (const item of data.items) {
            if (only && item.work_id !== only) continue;
            for (const pass of item.passes) for (const entry of pass.entries) if (entry.problem && entry.ts >= best[1]) best = [entry.key, entry.ts];
          }
          return best[0];
        }""",
        [run, only],
    )


def _selected_key(page) -> str:
    row = page.locator(SELECTED)
    return (row.get_attribute("data-entry") or row.get_attribute("data-slug")) if row.count() else ""


def test_a_failed_agent_turn_shows_once_in_the_whole_timeline_as_its_turn_row_marked_failed(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-once", broken=True)
    try:
        _open_all(page)
        expect(page.locator('#detail-panel .tl button.ev[data-entry="failed:ft"]')).to_have_count(0)
        turn = page.locator(f'#detail-panel .tl button.ev[data-slug="{BROKEN}"]')
        expect(turn).to_have_count(1)
        expect(turn).to_have_class(__import__("re").compile(r"\bbad\b"))
        assert "failed" in (turn.get_attribute("aria-label") or "")
    finally:
        _leave(page, context)


def test_the_problems_view_lists_a_failed_agent_turn_as_a_failed_row_and_offers_the_turn(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-offer", broken=True)
    try:
        _on(page)
        assert len(_keys(page)) == _count_of(page) == EXPECTED + 1
        expect(page.locator(f'#detail-panel .tl button.ev[data-slug="{BROKEN}"]')).to_have_count(0)
        row = page.locator('#detail-panel .tl button.ev[data-entry="failed:ft"]')
        expect(row).to_have_count(1)
        row.click()
        link = page.locator(".rd .rd-body").get_by_role("button", name="Open that turn")
        expect(link).to_have_count(1)
        link.click()
        expect(page.locator(SELECTED)).to_have_count(0)
        expect(page.locator(".rd")).to_contain_text("qa-story")
    finally:
        _leave(page, context)


def test_e_in_the_whole_timeline_stops_once_per_problem_with_a_failed_turn_counted_once(tmp_path):
    _live_, page, context, _name = _page(tmp_path, "prb-e-whole", broken=True)
    try:
        _open_all(page)
        count = _count_of(page)
        assert count == EXPECTED + 1
        page.locator(f'#detail-panel .tl button.ev[data-slug="{BROKEN}"]').click()
        seen = [BROKEN]
        for _step in range(count - 1):
            page.keyboard.press("e")
            page.wait_for_function("(old) => { const r = document.querySelector('#detail-panel .tl button.ev[aria-current=true]'); return (r.dataset.entry || r.dataset.slug) !== old; }", arg=seen[-1])
            seen.append(_selected_key(page))
        assert len(set(seen)) == count, seen
        page.keyboard.press("e")
        page.wait_for_function("(old) => { const r = document.querySelector('#detail-panel .tl button.ev[aria-current=true]'); return (r.dataset.entry || r.dataset.slug) !== old; }", arg=seen[-1])
        assert _selected_key(page) == BROKEN
    finally:
        _leave(page, context)


def test_pressing_problems_selects_and_reads_the_views_newest_row_when_the_selected_row_is_not_in_it(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, name = _page(tmp_path, "prb-select")
    try:
        _on(page)
        newest = _newest_problem(page, name)
        expect(page.locator(f'{SELECTED}[data-entry="{newest}"]')).to_have_count(1)
        expect(page.locator(".rd .rd-head")).to_be_visible()
    finally:
        _leave(page, context)


def test_a_selected_row_that_is_in_the_problems_view_stays_selected_and_turning_the_view_off_keeps_it(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-keep")
    try:
        _open_all(page)
        page.locator("#detail-panel .tl button.ev[data-kind=failed]").first.click()
        chosen = _selected_key(page)
        _on(page)
        assert _selected_key(page) == chosen
        page.locator(CHIP).click()
        expect(page.locator(CHIP)).to_have_attribute("aria-pressed", "false")
        assert _selected_key(page) == chosen
        _on(page)
        page.locator("#detail-panel .tl button.ev[data-kind=churn]").click()
        picked = _selected_key(page)
        page.locator(CHIP).click()
        assert _selected_key(page) == picked
    finally:
        _leave(page, context)


def test_a_row_hidden_by_the_item_filter_or_the_search_follows_the_same_rule_when_problems_is_pressed(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, name = _page(tmp_path, "prb-hidden")
    try:
        page.locator(SELECTOR).select_option(label="reset")
        _on(page)
        newest = _newest_problem(page, name, only="reset")
        expect(page.locator(f'{SELECTED}[data-entry="{newest}"]')).to_have_count(1)
        page.locator(CHIP).click()
        page.locator(SELECTOR).select_option(index=0)
        page.locator(SEARCH).fill("churn")
        _on(page)
        expect(page.locator(SELECTED)).to_have_attribute("data-kind", "churn")
    finally:
        _leave(page, context)


def test_opening_problems_from_the_attention_tile_selects_the_newest_problem_row(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, name = _page(tmp_path, "prb-tile-select", activity=False)
    try:
        page.locator(TILE).click()
        newest = _newest_problem(page, name)
        expect(page.locator(f'{SELECTED}[data-entry="{newest}"]')).to_have_count(1)
    finally:
        _leave(page, context)


def test_the_churn_row_and_its_pane_read_churn_in_every_activity_state_and_keep_churn_alert_in_the_accessible_name(tmp_path):
    from playwright.sync_api import expect

    _live_, page, context, _name = _page(tmp_path, "prb-churn-name")
    try:
        row = page.locator("#detail-panel .tl button.ev[data-kind=churn]")
        _open_all(page)
        expect(row.locator(".n")).to_have_text("CHURN")
        assert "churn alert" in (row.get_attribute("aria-label") or "")
        _on(page)
        expect(row.locator(".n")).to_have_text("CHURN")
        row.click()
        expect(page.locator(".rd .rd-head")).to_contain_text("CHURN")
        expect(page.locator(".rd .rd-body")).to_have_attribute("aria-label", "churn alert")
        page.locator(CHIP).click()
        page.locator(SEARCH).fill("poll")
        expect(row.locator(".n")).to_have_text("CHURN")
    finally:
        _leave(page, context)
