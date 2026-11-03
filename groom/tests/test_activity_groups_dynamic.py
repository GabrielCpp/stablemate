"""The Activity timeline grouped by work item and flow pass, measured on the page the operator gets."""
from __future__ import annotations

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from test_activity_groups import BASE, _pass, _polls, _seed
from test_activity_tab_dynamic import _open_activity, _pick, _run
from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _open,
    _scan,
    teardown_module,  # noqa: F401
)
from test_run_clock import span

from groom import store


@contextmanager
def _grouped(run: str, tmp: Path, *, running: bool = False, polls: int = 0) -> Iterator[str]:
    with _run(run, tmp, turns=False, running=running) as name:
        _seed(name)
        if polls:
            _polls(polls, name)
        yield name


def _heads(page, kind: str):
    return page.locator(f"#detail-panel .tl button.{kind}")


def _opened(tmp_path: Path, run: str, **kwargs):
    live = _live()
    assert live is not None, _UNAVAILABLE
    context = _grouped(run, tmp_path, **kwargs)
    name = context.__enter__()
    page = _open(live)
    _pick(page, name)
    _open_activity(page)
    return page, context


def _open_all(page) -> None:
    for number in range(_heads(page, "tl-group").count()):
        head = _heads(page, "tl-group").nth(number)
        if head.get_attribute("aria-expanded") == "false":
            head.click()
    for number in range(_heads(page, "tl-flow").count()):
        head = _heads(page, "tl-flow").nth(number)
        if head.get_attribute("aria-expanded") == "false":
            head.click()


def test_each_work_item_gets_a_heading_with_state_time_and_cost_and_only_the_one_in_progress_starts_open() -> None:
    from playwright.sync_api import expect

    page, context = _opened(Path(tempfile.mkdtemp()), "grp-items")
    try:
        heads = _heads(page, "tl-group")
        expect(heads).to_have_count(2)
        first, second = heads.nth(0), heads.nth(1)
        assert "sign-in" in first.inner_text() and "count unknown" in first.inner_text()
        assert "3m" in first.inner_text() and "$3.00" in first.inner_text()
        assert "reset" in second.inner_text() and "in progress" in second.inner_text() and "$3.00" in second.inner_text()
        expect(first).to_have_attribute("aria-expanded", "false")
        expect(second).to_have_attribute("aria-expanded", "true")
        label = first.get_attribute("aria-label") or ""
        assert label.startswith("Work item sign-in, count unknown, 3m, $3.00"), label
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_inside_a_work_item_each_flow_pass_gets_a_heading_with_state_time_and_cost() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-passes")
    try:
        _heads(page, "tl-group").nth(0).click()
        heads = _heads(page, "tl-flow")
        texts = [heads.nth(number).inner_text().lower() for number in range(heads.count())]
        assert "qa · 1st pass" in texts[0] and "2m" in texts[0] and "$2.00" in texts[0], texts
        assert "qa · 2nd pass" in texts[1] and "$1.00" in texts[1], texts
        label = heads.nth(0).get_attribute("aria-label") or ""
        assert label.startswith("qa · 1st pass, passed, 2m, $2.00"), label
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_finished_flow_pass_starts_folded_and_the_pass_holding_the_open_turn_starts_open() -> None:
    from playwright.sync_api import expect

    page, context = _opened(Path(tempfile.mkdtemp()), "grp-start")
    try:
        _heads(page, "tl-group").nth(0).click()
        for number in range(2):
            expect(_heads(page, "tl-flow").nth(number)).to_have_attribute("aria-expanded", "false")
        expect(_heads(page, "tl-flow").nth(2)).to_have_attribute("aria-expanded", "true")
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_selecting_a_heading_opens_or_closes_it_by_pointer_and_by_keyboard() -> None:
    from playwright.sync_api import expect

    page, context = _opened(Path(tempfile.mkdtemp()), "grp-toggle")
    try:
        first = _heads(page, "tl-group").nth(0)
        first.click()
        expect(first).to_have_attribute("aria-expanded", "true")
        first.click()
        expect(first).to_have_attribute("aria-expanded", "false")
        first.focus()
        page.keyboard.press("Enter")
        expect(first).to_have_attribute("aria-expanded", "true")
        flow = _heads(page, "tl-flow").nth(0)
        flow.focus()
        page.keyboard.press("Space")
        expect(flow).to_have_attribute("aria-expanded", "true")
        page.keyboard.press("Space")
        expect(flow).to_have_attribute("aria-expanded", "false")
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_node_that_runs_twice_has_two_rows_one_per_visit() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-visits")
    try:
        _open_all(page)
        rows = page.locator("#detail-panel .tl button.ev.turn")
        assert rows.count() == 3
        assert sum("qa-story" in rows.nth(number).inner_text() for number in range(3)) == 3
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_run_of_passed_steps_folds_to_one_line_and_selecting_it_opens_and_closes_one_row_per_step() -> None:
    from playwright.sync_api import expect

    page, context = _opened(Path(tempfile.mkdtemp()), "grp-fold")
    try:
        _open_all(page)
        fold = page.locator("#detail-panel .tl button.ev.steps").first
        assert fold.inner_text().split("\n")[-1].strip() == "2 steps · 11s · all passed" or "2 steps · 11s · all passed" in fold.inner_text()
        expect(fold).to_have_attribute("aria-expanded", "false")
        assert page.locator("#detail-panel .tl button.ev.step").count() == 0
        fold.click()
        expect(fold).to_have_attribute("aria-expanded", "true")
        steps = page.locator("#detail-panel .tl button.ev.step")
        expect(steps).to_have_count(2)
        assert "lint" in steps.nth(0).inner_text() and "build" in steps.nth(1).inner_text()
        fold.click()
        expect(fold).to_have_attribute("aria-expanded", "false")
        expect(page.locator("#detail-panel .tl button.ev.step")).to_have_count(0)
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_failed_step_stands_as_its_own_row_between_two_folds() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-failed")
    try:
        _open_all(page)
        first = page.locator("#detail-panel [data-pass^='pass:sign-in|qa|1']")
        kinds = first.evaluate("(node) => [...node.querySelectorAll('button.ev')].map((b) => b.dataset.kind || (b.dataset.fold ? 'steps' : 'turn'))")
        assert kinds[:3] == ["steps", "failed", "steps"], kinds
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_failed_step_a_gate_a_retry_and_a_churn_alert_each_get_a_row_with_a_different_mark() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-marks", polls=5)
    try:
        _open_all(page)
        marks = {}
        for kind in ("failed", "gate", "retry", "churn"):
            row = page.locator(f"#detail-panel .tl button.ev[data-kind='{kind}']")
            assert row.count() == 1, kind
            marks[kind] = row.locator(".i").inner_text()
        turn_mark = page.locator("#detail-panel .tl button.ev.turn .i").first.inner_text()
        assert marks["failed"] == "✕" and marks["gate"] == "?" and marks["retry"] == "!" and marks["churn"] == "!"
        assert len({marks["failed"], marks["gate"], marks["retry"], turn_mark}) == 4
        names = {kind: page.locator(f"#detail-panel .tl button.ev[data-kind='{kind}'] .n").inner_text() for kind in marks}
        assert names == {"failed": "test", "gate": "operator gate", "retry": "backend retry", "churn": "CHURN"}
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_selecting_a_problem_row_shows_its_name_its_time_and_its_one_line_result_in_the_pane() -> None:
    from playwright.sync_api import expect

    page, context = _opened(Path(tempfile.mkdtemp()), "grp-stub", polls=5)
    try:
        _open_all(page)
        wanted = {
            "failed": ("test", "2 tests failed"),
            "gate": ("operator gate", "escalation #1: docs block · answered"),
            "retry": ("backend retry", "The backend started the qa-story turn again after the attempt before it ended. It waited 30s first."),
            "churn": ("CHURN", "poll has run 5 times in a row on reset with the same labels."),
        }
        for kind, (name, result) in wanted.items():
            _open_all(page)
            row = page.locator(f"#detail-panel .tl button.ev[data-kind='{kind}']")
            row.click()
            expect(row).to_have_attribute("aria-current", "true")
            head = page.locator(".rd .rd-head")
            expect(head).to_contain_text(name)
            if kind in ("retry", "churn"):
                expect(head).to_contain_text(row.locator(".t").inner_text())
            expect(page.locator(".rd .rd-body")).to_contain_text(result.removesuffix(" · answered"))
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_selecting_a_turn_inside_a_group_reads_as_it_did() -> None:
    from playwright.sync_api import expect

    page, context = _opened(Path(tempfile.mkdtemp()), "grp-turn")
    try:
        _open_all(page)
        turns = page.locator("#detail-panel .tl button.ev.turn")
        turns.nth(0).click()
        expect(page.locator(".rd .rd-head")).to_contain_text("qa-story")
        expect(turns.nth(0)).to_have_attribute("aria-current", "true")
        assert page.locator("#detail-panel .tl button[aria-current='true']").count() == 1
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_the_running_turn_has_its_own_mark_as_the_last_row_of_its_flow_pass() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-live", running=True)
    try:
        last = page.locator("#detail-panel [data-pass] ").last
        rows = last.locator("button.ev")
        final = rows.nth(rows.count() - 1)
        assert final.locator(".i").inner_text() == "●"
        assert "live" in (final.get_attribute("class") or "")
        label = final.get_attribute("aria-label") or ""
        assert ", running," in label, label
        assert "running" in _heads(page, "tl-flow").last.inner_text()
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_heading_stays_in_view_while_its_rows_scroll() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-sticky")
    try:
        _open_all(page)
        page.evaluate("document.querySelector('#detail-panel .tl').style.maxHeight = '170px'")
        page.evaluate("document.querySelector('#detail-panel .tl').scrollTop = 120")
        box = page.evaluate("""() => {
          const tl = document.querySelector('#detail-panel .tl').getBoundingClientRect();
          return [...document.querySelectorAll('#detail-panel .tl button.tl-group')].map((h) => [h.getBoundingClientRect().top - tl.top, h.getBoundingClientRect().bottom - tl.top]);
        }""")
        assert any(abs(top) < 2 for top, _ in box), box
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_a_run_with_no_work_items_groups_its_rows_directly_under_the_flow_pass() -> None:
    from playwright.sync_api import expect

    live = _live()
    assert live is not None, _UNAVAILABLE
    with _run("grp-flat", Path(tempfile.mkdtemp()), turns=False) as run:
        spans = [span("r1", "t1", "", "coder", "run:coder", BASE, 900, {}, 1, run), *_pass("a", "qa", BASE + 10, "", [("lint", 5, "UNSET")], turn=(100, 2.0))]
        for one in spans:
            one["run_id"] = run
        store.insert_spans(spans)
        page = _open(live)
        try:
            _pick(page, run)
            _open_activity(page)
            expect(_heads(page, "tl-group")).to_have_count(0)
            expect(_heads(page, "tl-flow")).to_have_count(1)
            expect(_heads(page, "tl-flow").first).to_contain_text("qa · 1st pass")
        finally:
            page.close()


def test_a_heading_adds_up_to_the_overview_figures_for_its_work_item() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-figures")
    try:
        heading = _heads(page, "tl-group").nth(1).inner_text()
        page.get_by_role("tab", name="Overview").click()
        page.get_by_role("button", name="By work item").click()
        page.wait_for_selector("table[aria-label='Time and cost per work item']", timeout=10000)
        row = page.locator("table[aria-label='Time and cost per work item'] tbody tr", has_text="reset").first.inner_text()
        assert "$3.00" in heading and "$3.00" in row
        assert "1m" in heading and "1m 10s" in row
    finally:
        page.close()
        context.__exit__(None, None, None)


def test_headings_and_rows_keep_a_role_a_name_and_state_in_words_and_pass_an_axe_scan() -> None:
    page, context = _opened(Path(tempfile.mkdtemp()), "grp-a11y", running=True, polls=5)
    try:
        _open_all(page)
        for head in _heads(page, "tl-group").all() + _heads(page, "tl-flow").all():
            assert head.get_attribute("aria-label") and head.get_attribute("aria-expanded") in ("true", "false")
        for row in page.locator("#detail-panel .tl button.ev").all():
            label = row.get_attribute("aria-label") or ""
            assert any(word in label for word in ("finished", "running", "failed step", "operator gate", "backend retry", "churn alert", "step passed", "all passed")), label
        violations = _scan(page)
        assert violations == [], violations
    finally:
        page.close()
        context.__exit__(None, None, None)
