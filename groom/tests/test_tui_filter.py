from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from pathlib import Path

import _tui_support as support
import pytest
from textual.pilot import Pilot
from textual.widgets import Input, OptionList, Static

from groom import state
from groom.models import WorkflowState
from groom.tui import store as client
from groom.tui.app import GroomTui

ASSETS = Path(__file__).resolve().parents[1] / "groom" / "assets"
NODE = shutil.which("node")

ROW = {
    "name": "Alpha", "repo": "Beta", "type": "Gamma", "node": "Delta", "activity": "Epsilon",
    "doing": "Zeta", "question": "Eta", "run_id": "Theta", "id": "Iota", "state": "Kappa",
}

_HARNESS = """
import { readFileSync } from "node:fs";
const src = readFileSync(process.env.GROOM_JS, "utf8");
const start = src.indexOf("function rowHaystack");
const end = src.indexOf("}\\n", start) + 1;
const rowHaystack = new Function(src.slice(start, end) + "\\nreturn rowHaystack;")();
console.log(JSON.stringify(JSON.parse(process.env.GROOM_ROWS).map((row) => rowHaystack(row))));
"""


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


@asynccontextmanager
async def _booted(link: support.FakeLink) -> AsyncIterator[tuple[GroomTui, Pilot]]:
    app = GroomTui(link)
    async with app.run_test(size=(140, 40)) as pilot:
        yield app, pilot


def _run(scenario: Callable[[], Coroutine[None, None, None]]) -> None:
    asyncio.run(scenario())


def _names(app: GroomTui) -> list[str]:
    listing = app.query_one("#runs", OptionList)
    return [str(listing.get_option_at_index(i).prompt) for i in range(listing.option_count)]


def _highlighted_id(app: GroomTui) -> str:
    listing = app.query_one("#runs", OptionList)
    assert listing.highlighted is not None
    return str(listing.get_option_at_index(listing.highlighted).id)


def _status(app: GroomTui) -> str:
    return str(app.query_one("#status", Static).content)


def _note(app: GroomTui) -> str:
    return str(app.query_one("#runs-note", Static).content)


async def _loaded(link: support.FakeLink, app: GroomTui) -> None:
    link.push(support.state_frame())
    await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)


def test_each_haystack_field_is_searched():
    for field in client.HAYSTACK_FIELDS:
        row = {"id": "x", field: "needle"}
        assert client.filter_runs([row], "needle") == (row,), field
    assert client.filter_runs([{"id": "x", "state": "needle", "live": "needle"}], "needle") == ()


def test_the_query_is_trimmed_and_case_insensitive():
    rows = [{"id": "a", "name": "Coder-Acme"}, {"id": "b", "name": "author-globex"}]
    assert [r["id"] for r in client.filter_runs(rows, "  ACME ")] == ["a"]
    assert [r["id"] for r in client.filter_runs(rows, "oB")] == ["b"]


def test_an_empty_or_blank_query_keeps_every_run():
    rows = [{"id": "a", "name": "one"}, {"id": "b", "name": "two"}]
    assert client.filter_runs(rows, "") == tuple(rows)
    assert client.filter_runs(rows, "   ") == tuple(rows)


def test_a_query_matches_across_the_joined_fields_only_with_the_separator():
    row = {"id": "a", "name": "alpha", "repo": "beta"}
    assert client.filter_runs([row], "alpha beta") == (row,)
    assert client.filter_runs([row], "alphabeta") == ()


def test_a_missing_or_null_field_adds_nothing_to_the_haystack():
    assert client.row_haystack({"name": "a", "repo": None}) == "a " + " " * 6
    assert client.row_haystack({}) == " " * 7


def test_the_field_list_equals_the_dashboards_row_haystack():
    src = (ASSETS / "dashboard.js").read_text()
    start = src.index("function rowHaystack")
    body = src[start:src.index("\n}\n", start)]
    listed = re.search(r"return \[(.*?)\]\s*\.join\(\" \"\)\s*\.toLowerCase\(\)", body, re.S)
    assert listed is not None
    fields = tuple(part.strip().removeprefix("run.") for part in listed.group(1).split(","))
    assert fields == client.HAYSTACK_FIELDS


def test_the_haystack_equals_the_dashboards_on_sample_rows():
    if NODE is None:
        print("SKIP  node not on PATH — haystack parity not exercised", file=sys.stderr)
        return
    rows = [ROW, {**ROW, "question": None}, {"name": "Only"}, {**ROW, "run_id": 7}]
    result = subprocess.run(
        [NODE, "--input-type=module", "-e", _HARNESS],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "GROOM_JS": str(ASSETS / "dashboard.js"), "GROOM_ROWS": json.dumps(rows)},
    )
    assert result.returncode == 0, result.stderr
    assert [client.row_haystack(row) for row in rows] == json.loads(result.stdout)


def test_slash_and_typing_filter_the_list_and_keep_the_highlight():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            assert app.query_one("#filter", Input).display is False
            await pilot.press("j")
            assert _highlighted_id(app) == support.GLOBEX
            await pilot.press("/")
            assert app.query_one("#filter", Input).display is True
            assert app.focused is app.query_one("#filter", Input)
            await pilot.press("c", "o", "d", "e", "r")
            await support.until(lambda: len(_names(app)) == 2)
            assert [support.ACME, support.WEBAPP] == [
                str(app.query_one("#runs", OptionList).get_option_at_index(i).id) for i in range(2)
            ]
            assert _highlighted_id(app) == support.ACME
            assert link.sent == []
            assert link.gets == []

    _run(scenario)


def test_the_highlight_follows_the_run_that_still_matches():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("/", "c", "o", "d", "e", "r")
            await support.until(lambda: len(_names(app)) == 2)
            app.query_one("#runs", OptionList).highlighted = 1
            await pilot.press("-")
            await support.until(lambda: _highlighted_id(app) == support.WEBAPP)

    _run(scenario)


def test_enter_moves_focus_to_the_list_on_the_first_match():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("/", "c", "o", "d", "e", "r")
            await support.until(lambda: len(_names(app)) == 2)
            app.query_one("#runs", OptionList).highlighted = 1
            await pilot.press("enter")
            assert app.focused is app.query_one("#runs", OptionList)
            assert _highlighted_id(app) == support.ACME
            assert app.query_one("#filter", Input).display is True
            assert len(_names(app)) == 2

    _run(scenario)


def test_escape_clears_the_query_hides_the_input_and_returns_to_the_list():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("/", "g", "l", "o", "b")
            await support.until(lambda: len(_names(app)) == 1)
            await pilot.press("escape")
            await support.until(lambda: len(_names(app)) == 3)
            assert app.store.query == ""
            assert app.query_one("#filter", Input).display is False
            assert app.focused is app.query_one("#runs", OptionList)

    _run(scenario)


def test_a_state_frame_while_filtering_keeps_the_filter_applied():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("/", "g", "l", "o", "b")
            await support.until(lambda: len(_names(app)) == 1)
            state.upsert_workflow(
                "globex7890ab", name="author-globex-two", workflow_type="author", repo_name="globex",
                run_id="run-two", state=WorkflowState.RUNNING,
            )
            link.push(support.state_frame())
            await support.until(lambda: "filter: glob  2 of 4" in _status(app))
            assert len(_names(app)) == 2
            assert all("author-globex" in name for name in _names(app))

    _run(scenario)


def test_a_query_with_no_match_says_so_in_the_list_area():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            assert _note(app) == ""
            await pilot.press("/", "z", "z", "z")
            await support.until(lambda: _note(app) != "")
            assert _note(app) == "No run matches “zzz”."
            assert _names(app) == []
            await pilot.press("escape")
            await support.until(lambda: _note(app) == "")

    _run(scenario)


def test_an_empty_fleet_keeps_its_own_text_when_not_filtering():
    async def scenario() -> None:
        link = support.FakeLink()
        state.WORKFLOWS.clear()
        async with _booted(link) as (app, _pilot):
            link.push(support.state_frame())
            await support.until(lambda: "No workhorse runs" in _status(app))
            assert _note(app) == ""

    _run(scenario)


def test_the_open_run_stays_open_when_the_filter_hides_its_row():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("enter")
            await support.until(lambda: link.sent)
            link.push(support.detail_frame(support.ACME))
            await support.until(lambda: app.store.detail is not None)
            await pilot.press("/", "g", "l", "o", "b")
            await support.until(lambda: len(_names(app)) == 1)
            assert app.store.selected == support.ACME
            assert app.store.detail is not None
            assert "coder-acme" in str(app.pane.query_one("#head", Static).content)

    _run(scenario)


def test_the_status_line_counts_the_matches_while_a_query_is_set():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            assert "filter:" not in _status(app)
            await pilot.press("/", "c", "o", "d", "e", "r")
            await support.until(lambda: "filter: coder  2 of 3" in _status(app))
            await pilot.press("escape")
            await support.until(lambda: "filter:" not in _status(app))

    _run(scenario)
