from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _post_turn,
    _scan,
    _seconds_in,
    teardown_module,  # noqa: F401
)
from test_run_clock import three_sessions

LONG = "/home/acme/work/" + "/".join(["deeply-nested-directory-name"] * 8) + "/api-service"
SECTIONS = ("#detail-wall-clock", "#detail-models", "#detail-facts", "#detail-sessions")


@contextmanager
def _run(run: str, *, native: bool = True, state: str = "running", path: str = "/home/acme/work/api-service", spans: list[dict] | None = None) -> Iterator[str]:
    from groom import state as groom_state
    from groom import store
    from groom.models import WorkflowState

    container = f"{run}-box"[:12].ljust(12, "x")
    seeded = three_sessions(time.time() - 3000.0, run) if spans is None else spans
    store.insert_spans([
        {**row, "span_id": f"{run}-{row['span_id']}", "trace_id": f"{run}-{row['trace_id']}",
         "parent_id": f"{run}-{row['parent_id']}" if row["parent_id"] else ""}
        for row in seeded
    ])
    groom_state.upsert_workflow(
        container, name=f"coder-{run}", workflow_type="coder", repo_name="acme", repo_branch="main",
        current_node="dev", activity="working", run_id=run, state=WorkflowState(state), native=native,
        workspace_volume=path,
    )
    try:
        yield run
    finally:
        groom_state.WORKFLOWS.pop(container, None)
        store.delete_run_telemetry(run)


def _pick(page, run: str) -> None:
    page.locator("#runs-list .row", has_text=run).first.click()


def _table(page, name: str) -> list[list[str]]:
    rows = page.get_by_role("table", name=name).locator("tbody tr")
    return [[cell.strip() for cell in row.locator("td").all_inner_texts()] for row in rows.all()]


def _stub_clipboard(page, outcome: str) -> None:
    page.evaluate(
        """(outcome) => {
          window.__copied = [];
          const writeText = (text) => outcome === "ok"
            ? (window.__copied.push(text), Promise.resolve())
            : Promise.reject(new Error("denied"));
          Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
        }""",
        outcome,
    )


def test_the_legend_names_six_segments_in_words_and_the_active_ones_equal_the_active_tile():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-legend") as run:
        page = _open(live)
        try:
            _pick(page, run)
            legend = page.locator("#detail-wall-clock ul.legend li")
            expect(legend).to_have_count(6)
            seconds = {
                key: float(value)
                for key, value in legend.evaluate_all("els => els.map((el) => [el.dataset.segment, el.dataset.seconds])")
            }
            assert set(seconds) == {"agent", "deterministic", "infra", "wait", "unclassified", "resume_gap"}
            text = page.locator("#detail-wall-clock").inner_text()
            for name in ("Agent turns", "Deterministic", "Infra", "Waits", "Unclassified", "Stopped between sessions"):
                assert name in text, text
            assert seconds["agent"] == 360 and seconds["resume_gap"] == 800
            active = _seconds_in(page.locator("#detail-active-tile .vv").inner_text())
            assert abs(seconds["agent"] + seconds["deterministic"] + seconds["infra"] - active) <= 1
            assert page.locator("#detail-wall-clock .tbar").get_attribute("role") == "img"
        finally:
            page.close()


def test_the_models_table_says_not_reported_for_a_model_with_no_cost_and_totals_the_cost():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-models") as run:
        page = _open(live)
        try:
            _pick(page, run)
            expect(page.get_by_role("table", name="Models")).to_be_visible()
            rows = {row[0]: row for row in _table(page, "Models")}
            haiku = next(row for name, row in rows.items() if "haiku" in name)
            sonnet = next(row for name, row in rows.items() if "sonnet" in name)
            assert "not reported" in haiku[2] and "$0" not in haiku[2], haiku
            assert "$3.50" in sonnet[2], sonnet
            assert haiku[1] == "2" and sonnet[1] == "2"
            assert "$3.50" in page.locator("#detail-cost-tile").inner_text()
        finally:
            page.close()


def test_the_sessions_table_has_the_tiles_count_and_says_when_no_ending_was_recorded():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-sessions") as run:
        page = _open(live)
        try:
            _pick(page, run)
            expect(page.get_by_role("table", name="Sessions")).to_be_visible()
            rows = _table(page, "Sessions")
            tile = re.search(r"(\d+) sessions?", page.locator("#detail-active-tile").inner_text())
            assert tile is not None
            assert len(rows) == int(tile.group(1)) == 3
            assert "interrupted" in rows[0][4]
            assert "no recorded ending" in rows[1][4]
            assert rows[2][3] == "still running" and rows[2][4] == "running"
        finally:
            page.close()


def test_a_run_that_is_no_longer_live_does_not_claim_its_last_session_is_running():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-ended", state="finished") as run:
        page = _open(live)
        try:
            _pick(page, run)
            expect(page.get_by_role("table", name="Sessions")).to_be_visible()
            rows = _table(page, "Sessions")
            assert "no recorded ending" in rows[2][4]
            assert "running" not in rows[2][3]
        finally:
            page.close()


def test_the_checkout_path_shows_for_a_native_run_and_a_long_one_stays_in_the_pane():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-native", path=LONG) as native:
        page = _open(live)
        try:
            _pick(page, native)
            facts = page.locator("#detail-facts")
            expect(facts).to_contain_text("Checkout")
            expect(facts).to_contain_text("api-service")
            fits = page.evaluate(
                "() => { const p = document.querySelector('#detail-facts'); const pane = p.closest('[role=tabpanel]');"
                " return p.scrollWidth <= p.clientWidth + 1 && pane.scrollWidth <= pane.clientWidth + 1; }"
            )
            assert fits
        finally:
            page.close()


def test_a_copy_button_works_from_the_keyboard_and_confirms_in_text_a_screen_reader_announces():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-copy") as run:
        page = _open(live)
        try:
            _pick(page, run)
            _stub_clipboard(page, "ok")
            button = page.get_by_role("button", name="Copy run id")
            button.focus()
            page.keyboard.press("Enter")
            note = page.locator("#detail-facts .copy-note[role=status]").first
            expect(page.locator("#detail-facts").get_by_text("Copied run id")).to_be_visible()
            assert page.evaluate("() => window.__copied") == [run]
            assert note.count() == 1
            page.get_by_role("button", name="Copy branch").focus()
            page.keyboard.press("Space")
            expect(page.locator("#detail-facts").get_by_text("Copied branch")).to_be_visible()
            assert page.evaluate("() => window.__copied") == [run, "story/acme-sign-in"]
        finally:
            page.close()


def test_a_failed_clipboard_write_says_so():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-nocopy") as run:
        page = _open(live)
        try:
            _pick(page, run)
            _stub_clipboard(page, "denied")
            page.get_by_role("button", name="Copy run id").click()
            expect(page.locator("#detail-facts").get_by_text("Could not copy run id")).to_be_visible()
            expect(page.locator("#detail-facts").get_by_text("Copied run id")).to_have_count(0)
        finally:
            page.close()


def test_a_run_with_no_finished_node_shows_only_its_run_facts_of_the_new_sections():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-empty", spans=[]) as run:
        page = _open(live)
        try:
            _pick(page, run)
            expect(page.get_by_role("tabpanel")).to_contain_text("finishes")
            for selector in SECTIONS:
                if selector == "#detail-facts":
                    expect(page.locator(selector)).to_contain_text("/home/acme/work/api-service")
                else:
                    expect(page.locator(selector)).to_have_count(0)
        finally:
            page.close()


def test_a_live_refresh_keeps_the_scroll_position_with_the_new_sections_open():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-scroll", state="finished") as run:
        page = _open(live)
        try:
            page.set_viewport_size({"width": 1400, "height": 330})
            _pick(page, run)
            panel = page.get_by_role("tabpanel")
            expect(page.locator("#detail-sessions")).to_be_attached()
            scroller = panel.locator(".ov").first
            scroller.evaluate("el => { el.scrollTop = 120; }")
            assert scroller.evaluate("el => el.scrollTop") == 120
            mark = "() => document.querySelector('#detail-wall-clock').getBoundingClientRect().top"
            placed = page.evaluate(mark)
            turns = int(page.locator("#detail-turns-tile .vv").inner_text())
            _post_turn(live, "00000000000000d1", usd=0.5, run=run, workflow="coder", node="dev")
            expect(page.locator("#detail-turns-tile .vv")).to_have_text(str(turns + 1), timeout=15000)
            assert abs(page.evaluate(mark) - placed) <= 1
            expect(page.locator("#detail-sessions")).to_be_attached()
        finally:
            page.close()


def test_the_new_sections_pass_axe():
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("clock-axe") as run:
        page = _open(live)
        try:
            _pick(page, run)
            for selector in SECTIONS:
                expect(page.locator(selector)).to_be_attached()
            _stub_clipboard(page, "ok")
            page.get_by_role("button", name="Copy run id").click()
            expect(page.locator("#detail-facts").get_by_text("Copied run id")).to_be_visible()
            assert not _scan(page)
        finally:
            page.close()
