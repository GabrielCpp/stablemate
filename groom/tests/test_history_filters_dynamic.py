from __future__ import annotations

import json
import re

from test_a11y_dynamic import (
    _UNAVAILABLE,
    _live,
    _scan,
    teardown_module,  # noqa: F401
)
from test_history_dynamic import TABLE, _history, _history_page, _open_history, _row, _totals
from test_history_open_dynamic import AXE, DETAIL, LONG_REPO, LONG_RUN, _ended, _long_names, _opened

BAR = "#history .h-top"
NARROW = "#history .row"
EMPTY = "#history .empty-big"
CHOICES = {"Workflow": "workflow", "Repo": "repo", "Ending": "ending", "Range": "range"}


def _rows() -> list[dict]:
    return [
        _row("hist-a", 1, workflow="coder", repo="acme", cost_usd=100.0, active_s=3600.0),
        _row("hist-b", 2, workflow="author", repo="globex", ending="failed", cost_usd=50.5, active_s=1800.0),
        _row("hist-c", 3, workflow="coder", repo="globex", ending="failed", cost_usd=None, est_usd=31.2, priced_turns=0, turns=9, active_s=600.0),
        _row("hist-d", 9 * 24, workflow="okf-book", repo="acme", ending="none", cost_usd=20.0, priced_turns=1, turns=2, active_s=0.0),
    ]


def _shown(page) -> list[str]:
    return [row[0].split()[-1] for row in page.get_by_role("table", name=TABLE).locator("tbody tr").evaluate_all(
        "(rows) => rows.map((row) => [row.dataset.run])"
    )]


def _narrowed(page) -> list[str]:
    return page.locator(NARROW).evaluate_all("(rows) => rows.map((row) => row.dataset.run)")


def _choose(page, name: str, option: str) -> None:
    page.get_by_role("combobox", name=name).select_option(label=option)


def _api_requests_after_the_table(page) -> list[str]:
    asked: list[str] = []
    page.on("request", lambda request: asked.append(request.url) if "/api/" in request.url else None)
    page.wait_for_selector("#history table.ht", timeout=10000)
    asked.clear()
    return asked


def _options(page, name: str) -> list[str]:
    return page.get_by_role("combobox", name=name).locator("option").all_inner_texts()


def _picked(page, name: str) -> str:
    return page.get_by_role("combobox", name=name).evaluate("(el) => el.selectedOptions[0].textContent")


def _narrow(page, run: str) -> None:
    page.locator("#history tr.hrow", has_text=run).click()
    page.wait_for_selector(f"{DETAIL} .dtabs", timeout=15000)


def test_the_workflow_and_repo_filters_offer_the_values_in_the_list_each_with_an_all_choice():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            workflows = _options(page, "Workflow")
            repos = _options(page, "Repo")
            chosen = (_picked(page, "Workflow"), _picked(page, "Repo"))
        finally:
            page.close()
    assert workflows == ["All workflows", "author", "coder", "okf-book"]
    assert repos == ["All repos", "acme", "globex"]
    assert chosen == ("All workflows", "All repos")


def test_the_ending_filter_offers_every_ending_in_words_with_an_any_choice():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(_row("hist-a", 1)):
        page = _history_page(live)
        try:
            endings = _options(page, "Ending")
            chosen = _picked(page, "Ending")
        finally:
            page.close()
    assert endings == ["Any ending", "success", "gave up", "failed", "interrupted", "crashed", "no ending recorded"]
    assert chosen == "Any ending"


def test_the_range_filter_offers_the_last_7_and_30_days_starts_on_30_and_narrows_to_7():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            ranges = _options(page, "Range")
            start = _picked(page, "Range")
            before = _shown(page)
            _choose(page, "Range", "Last 7 days")
            after = _shown(page)
            again = _totals(page)[0]
        finally:
            page.close()
    assert ranges == ["Last 30 days", "Last 7 days"]
    assert start == "Last 30 days"
    assert before == ["hist-a", "hist-b", "hist-c", "hist-d"]
    assert after == ["hist-a", "hist-b", "hist-c"]
    assert again == "3 runs"


def test_the_text_filter_narrows_rows_by_run_or_repo_as_the_operator_types():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            box = page.get_by_role("searchbox", name="Filter history")
            box.press_sequentially("hist-")
            stem = _shown(page)
            box.press_sequentially("b")
            by_run = _shown(page)
            box.fill("")
            box.press_sequentially("GLOB")
            by_repo = _shown(page)
            totals = _totals(page)[0]
        finally:
            page.close()
    assert stem == ["hist-a", "hist-b", "hist-c", "hist-d"]
    assert by_run == ["hist-b"]
    assert by_repo == ["hist-b", "hist-c"]
    assert totals == "2 runs"


def test_each_filter_narrows_the_rows_at_once_and_filters_combine_without_a_request():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _open_history(live)
        try:
            asked = _api_requests_after_the_table(page)
            _choose(page, "Workflow", "coder")
            by_workflow = _shown(page)
            _choose(page, "Repo", "globex")
            with_repo = _shown(page)
            _choose(page, "Ending", "success")
            with_ending = _shown(page)
            _choose(page, "Ending", "failed")
            failed = _shown(page)
            page.get_by_role("searchbox", name="Filter history").fill("nothing-like-this")
            with_text = _shown(page) if page.locator("table.ht").count() else []
            page.wait_for_timeout(300)
        finally:
            page.close()
    assert by_workflow == ["hist-a", "hist-c"]
    assert with_repo == ["hist-c"]
    assert with_ending == []
    assert failed == ["hist-c"]
    assert with_text == []
    assert not [url for url in asked if "/api/history" in url]


def test_the_totals_describe_the_rows_shown_with_the_estimate_partly_priced_and_reading_clauses():
    live = _live()
    assert live is not None, _UNAVAILABLE
    pending = _row("hist-p", 4, workflow="coder", repo="acme", state="pending", ending="", cost_usd=None, active_s=0.0, priced_turns=0, turns=0)
    with _history(*_rows(), pending):
        page = _history_page(live)
        try:
            everything = _totals(page)
            _choose(page, "Workflow", "coder")
            coder = _totals(page)
            _choose(page, "Workflow", "All workflows")
            _choose(page, "Workflow", "okf-book")
            book = _totals(page)
            _choose(page, "Workflow", "All workflows")
            _choose(page, "Ending", "success")
            winners = _totals(page)
        finally:
            page.close()
    assert everything == ["5 runs", "$201.70 spent, $31.20 of it an estimate, 1 run partly priced, 1 summary still being read", "1h 40m active", "1 of 4 ended in success"]
    assert coder == ["3 runs", "$131.20 spent, $31.20 of it an estimate, 1 summary still being read", "1h 10m active", "1 of 2 ended in success", "— median per coder item: only 1 comparable run, and it takes 5"]
    assert book == ["1 run", "$20.00 spent, 1 run partly priced", "0m active", "0 of 1 ended in success", "— median per okf-book item: no comparable run yet, and it takes 5"]
    assert winners == ["1 run", "$100.00 spent", "1h active", "1 of 1 ended in success"]


def test_selecting_a_run_keeps_the_filters_and_states_them_above_the_narrowed_list():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            page.get_by_role("searchbox", name="Filter history").fill("hist")
            _choose(page, "Workflow", "coder")
            _choose(page, "Ending", "failed")
            _choose(page, "Range", "Last 7 days")
            before = _shown(page)
            _narrow(page, "hist-c")
            rows = _narrowed(page)
            selected = page.locator(f"{NARROW}.selected").get_attribute("data-run")
            scope = page.locator(f"{BAR} .scope").inner_text()
            typed = page.get_by_role("searchbox", name="Filter history").input_value()
            selects = page.locator(f"{BAR} select").count()
        finally:
            page.close()
    assert before == ["hist-c"]
    assert rows == before and selected == "hist-c"
    assert scope == "coder, failed, last 7 days"
    assert typed == "hist"
    assert selects == 0


def test_the_narrowed_list_says_so_when_the_text_filter_leaves_it_empty_and_the_run_stays_open():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _opened(live, "hist-a")
        try:
            page.wait_for_selector(f"{DETAIL} .dtabs", timeout=15000)
            page.get_by_role("searchbox", name="Filter history").fill("zzz")
            message = page.locator(EMPTY).inner_text()
            rows = page.locator(NARROW).count()
            head = page.locator(f"{DETAIL} .run-id").inner_text()
            page.get_by_role("button", name="Clear the filters").click()
            back = _narrowed(page)
        finally:
            page.close()
    assert message.startswith("No runs match these filters.")
    assert rows == 0 and head == "hist-a"
    assert back == ["hist-a", "hist-b", "hist-c", "hist-d"]


def test_closing_the_run_returns_to_the_table_with_the_filters_still_set():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            _choose(page, "Repo", "globex")
            page.get_by_role("searchbox", name="Filter history").fill("hist-")
            expected = _shown(page)
            _narrow(page, "hist-b")
            page.get_by_role("button", name="Close run").click()
            page.wait_for_selector("#history table.ht")
            rows = _shown(page)
            repo = _picked(page, "Repo")
            typed = page.get_by_role("searchbox", name="Filter history").input_value()
            totals = _totals(page)[0]
        finally:
            page.close()
    assert expected == ["hist-b", "hist-c"]
    assert rows == expected and totals == "2 runs"
    assert repo == "globex" and typed == "hist-"


def test_leaving_history_for_another_tab_and_coming_back_keeps_the_filters_and_the_open_run():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            _choose(page, "Workflow", "coder")
            _choose(page, "Range", "Last 7 days")
            _narrow(page, "hist-c")
            page.click('.act-btn[data-mode="attend"]')
            page.click('.act-btn[data-mode="history"]')
            page.wait_for_selector(f"{NARROW}.selected", timeout=10000)
            rows = _narrowed(page)
            selected = page.locator(f"{NARROW}.selected").get_attribute("data-run")
            scope = page.locator(f"{BAR} .scope").inner_text()
            head = page.locator(f"{DETAIL} .run-id").inner_text()
            page.get_by_role("button", name="Close run").click()
            page.wait_for_selector("#history table.ht")
            workflow, window = _picked(page, "Workflow"), _picked(page, "Range")
        finally:
            page.close()
    assert rows == ["hist-a", "hist-c"] and selected == "hist-c"
    assert scope == "coder, last 7 days"
    assert head == "hist-c"
    assert (workflow, window) == ("coder", "Last 7 days")


def test_when_nothing_matches_the_pane_says_so_the_totals_read_zero_and_a_control_clears_the_filters():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            _choose(page, "Workflow", "author")
            _choose(page, "Repo", "acme")
            message = page.locator(EMPTY).inner_text()
            totals = _totals(page)
            tables = page.locator("#history table.ht").count()
            page.get_by_role("button", name="Clear the filters").click()
            rows = _shown(page)
            reset = [_picked(page, name) for name in CHOICES]
            focused = page.evaluate("document.activeElement.getAttribute('aria-label')")
        finally:
            page.close()
    assert message.startswith("No runs match these filters.")
    assert totals == ["0 runs", "$0.00 spent", "0m active"]
    assert tables == 0
    assert rows == ["hist-a", "hist-b", "hist-c", "hist-d"]
    assert reset == ["All workflows", "All repos", "Any ending", "Last 30 days"]
    assert focused == "Filter history"


def test_with_no_filter_set_the_table_and_the_narrowed_list_hold_every_run():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            table = _shown(page)
            clear = page.get_by_role("button", name="Clear the filters").count()
            _narrow(page, "hist-a")
            narrowed = _narrowed(page)
            scope = page.locator(f"{BAR} .scope").inner_text()
        finally:
            page.close()
    assert table == narrowed == ["hist-a", "hist-b", "hist-c", "hist-d"]
    assert clear == 0
    assert scope == "all workflows, last 30 days"


def test_every_filter_has_an_accessible_name_and_keyboard_operation():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()):
        page = _history_page(live)
        try:
            roles = {name: page.get_by_role("combobox", name=name).count() for name in CHOICES}
            box = page.get_by_role("searchbox", name="Filter history")
            box.focus()
            page.keyboard.type("hist-a")
            typed = _shown(page)
            box.fill("")
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.getAttribute('aria-label')")
            page.keyboard.press("ArrowDown")
            by_key = _shown(page)
            ordered = page.evaluate("Array.from(document.querySelectorAll('#history .h-top input, #history .h-top select')).map((el) => el.getAttribute('aria-label'))")
        finally:
            page.close()
    assert roles == {"Workflow": 1, "Repo": 1, "Ending": 1, "Range": 1}
    assert typed == ["hist-a"]
    assert focused == "Workflow"
    assert by_key == ["hist-b"]
    assert ordered == ["Filter history", "Workflow", "Repo", "Ending", "Range"]


def test_j_k_and_e_stay_inert_while_a_filter_holds_focus():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _ended(hist_b={}):
        page = _opened(live, "hist-a")
        try:
            page.wait_for_selector(f"{DETAIL} .dtabs", timeout=15000)
            page.get_by_role("tab", name=re.compile("^Activity")).click()
            page.wait_for_selector(f"{DETAIL} .tl button", timeout=15000)
            lit = f"{DETAIL} .tl button[aria-current=true]"
            before = page.locator(lit).evaluate_all("(rows) => rows.map((r) => r.dataset.entry || r.dataset.slug)")
            page.get_by_role("searchbox", name="Filter history").focus()
            for key in "jke":
                page.keyboard.press(key)
            after = page.locator(lit).evaluate_all("(rows) => rows.map((r) => r.dataset.entry || r.dataset.slug)")
            typed = page.get_by_role("searchbox", name="Filter history").input_value()
            head = page.locator(f"{DETAIL} .run-id").inner_text()
            tab = page.get_by_role("tab", selected=True).inner_text()
        finally:
            page.close()
    assert typed == "jke"
    assert after == before
    assert head == "hist-a"
    assert tab.startswith("Activity")


def test_the_filtered_history_has_no_accessibility_violations():
    live = _live()
    assert live is not None, _UNAVAILABLE
    with _history(*_rows()[:3]):
        page = _history_page(live)
        try:
            page.add_script_tag(path=str(AXE))
            _choose(page, "Workflow", "coder")
            table = _scan(page)
            _choose(page, "Repo", "acme")
            _choose(page, "Ending", "failed")
            empty = _scan(page)
        finally:
            page.close()
    with _ended(hist_b={}):
        page = _opened(live, "hist-a")
        try:
            page.wait_for_selector(f"{DETAIL} .ov", timeout=15000)
            page.add_script_tag(path=str(AXE))
            page.get_by_role("searchbox", name="Filter history").fill("hist")
            narrow = _scan(page)
        finally:
            page.close()
    assert not table, json.dumps(table, indent=1)
    assert not empty, json.dumps(empty, indent=1)
    assert not narrow, json.dumps(narrow, indent=1)


def test_a_long_run_id_and_repo_label_keep_the_filter_bar_inside_the_pane_at_one_width():
    live = _live()
    assert live is not None, _UNAVAILABLE
    run, repo = LONG_RUN, LONG_REPO
    with _long_names():
        page = _history_page(live)
        try:
            reach = "(el) => { const pane = document.querySelector('#history').getBoundingClientRect(); return Array.from(el.children).every((c) => c.getBoundingClientRect().right <= pane.right && c.getBoundingClientRect().left >= pane.left); }"
            widths = "Array.from(document.querySelectorAll('#history .h-top select')).map((el) => el.getBoundingClientRect().width)"
            before = page.evaluate(widths)
            _choose(page, "Repo", repo)
            _choose(page, "Ending", "no ending recorded")
            _choose(page, "Ending", "success")
            after = page.evaluate(widths)
            inside = page.locator(BAR).evaluate(reach)
            _narrow(page, run)
            scope = page.locator(f"{BAR} .scope").inner_text()
            narrow_inside = page.locator(BAR).evaluate(reach)
            width = page.locator("#history").evaluate("(el) => el.getBoundingClientRect().width")
            page.get_by_role("button", name="Close run").click()
            page.wait_for_selector("#history table.ht")
            _choose(page, "Repo", "All repos")
            _choose(page, "Ending", "Any ending")
            _narrow(page, "hist-b")
            other = page.locator("#history").evaluate("(el) => el.getBoundingClientRect().width")
            overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        finally:
            page.close()
    assert before == after
    assert inside and narrow_inside
    assert repo in scope
    assert width == other
    assert not overflow
