from __future__ import annotations

import asyncio
import re

import _changes_support as ch
import _tui_support as support
import pytest
from textual.widgets import OptionList

from groom import state
from groom.tui.route import route
from groom.tui.widgets.code import CodeView

CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


def test_d_fetches_the_repos_then_the_runs_diff_and_lists_the_files_with_counts():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            assert link.gets == ["/repos", ch.route_diff(support.GLOBEX, ch.API)]
            assert app.pane.tab == "diff"
            assert ch.diff_tab(app).display
            assert ch.diff_rows(app) == ["src/app.py  +1 -1", "README.md  +2 -0"]
            assert "author-globex/api-service" in ch.text_of(app, "#diff-repo")
            assert "(p to change)" in ch.text_of(app, "#diff-repo")
            assert ch.text_of(app, "#diff-view-note") == "Select a changed file to see its diff."

    ch.run(scenario)


def test_highlighting_the_second_file_shows_its_diff_with_no_request():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            assert app.query_one("#diff-files", OptionList).has_focus
            asked = len(link.gets)
            await pilot.press("down", "down")
            await pilot.pause()
            await support.until(lambda: "+# Title" in ch.code_of(app, "#diff-view"))
            assert "src/app.py" not in ch.code_of(app, "#diff-view")
            assert len(link.gets) == asked
            await pilot.press("up")
            await support.until(lambda: "+new line" in ch.code_of(app, "#diff-view"))

    ch.run(scenario)


def test_a_detail_push_keeps_the_diff_the_highlight_and_the_requests():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("down", "down")
            await support.until(lambda: "+# Title" in ch.code_of(app, "#diff-view"))
            before = ch.code_of(app, "#diff-view")
            asked = list(link.gets)
            seen = app.store.detail
            link.push(support.history_frame(support.GLOBEX, [support.log_row(100.0, "tick")]))
            await support.until(lambda: app.store.detail is not seen)
            await pilot.pause()
            assert link.gets == asked
            assert app.query_one("#diff-files", OptionList).highlighted == 1
            assert ch.code_of(app, "#diff-view") == before
            assert ch.diff_rows(app) == ["src/app.py  +1 -1", "README.md  +2 -0"]

    ch.run(scenario)


def test_each_press_of_d_reloads_the_diff():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("t", "d")
            await support.until(lambda: link.gets.count(ch.route_diff(support.GLOBEX, ch.API)) == 2)
            assert link.gets.count("/repos") == 1

    ch.run(scenario)


def test_an_empty_diff_says_there_are_no_changes():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[ch.route_diff(support.GLOBEX, ch.API)] = {"diff": ""}
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.text_of(app, "#diff-note") == "No changes.")
            assert ch.diff_rows(app) == []

    ch.run(scenario)


def test_a_failed_diff_says_why():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        del link.get_replies[ch.route_diff(support.GLOBEX, ch.API)]
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.text_of(app, "#diff-note").startswith("Could not load the diff: "))
            assert ch.diff_rows(app) == []

    ch.run(scenario)


def test_the_loading_note_shows_while_the_diff_is_in_flight():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.holds[ch.route_diff(support.GLOBEX, ch.API)] = held = asyncio.Event()
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.route_diff(support.GLOBEX, ch.API) in link.gets)
            assert ch.text_of(app, "#diff-note") == "Loading changes…"
            held.set()
            await support.until(lambda: ch.diff_rows(app))
            assert ch.text_of(app, "#diff-note") == ""

    ch.run(scenario)


def test_a_hostile_diff_reaches_the_widgets_without_control_bytes():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        hostile = (
            "diff --git a/bad\x9b31m.py b/bad\x9b31m.py\n--- a/bad\x9b31m.py\n+++ b/bad\x9b31m.py\n"
            "@@ -1 +1 @@\n-x\n+y\x1b]52;c;aGk=\x07z\x1b[2J\n"
        )
        link.get_replies[ch.route_diff(support.GLOBEX, ch.API)] = {"diff": hostile}
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("down")
            await support.until(lambda: ch.code_of(app, "#diff-view"))
            assert ch.diff_rows(app) == ["bad.py  +1 -1"]
            shown = ch.code_of(app, "#diff-view") + "".join(ch.diff_rows(app))
            assert "+yz" in shown
            assert not CONTROLS.search(shown)
            assert "52;c" not in shown

    ch.run(scenario)


def test_a_long_diff_shows_five_thousand_lines_and_a_note():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        body = "".join(f"+line {n}\n" for n in range(6000))
        big = f"diff --git a/big.txt b/big.txt\n--- /dev/null\n+++ b/big.txt\n@@ -0,0 +1,6000 @@\n{body}"
        link.get_replies[ch.route_diff(support.GLOBEX, ch.API)] = {"diff": big}
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("down")
            await support.until(lambda: ch.code_of(app, "#diff-view"))
            assert ch.diff_rows(app) == ["big.txt  +6000 -0"]
            assert app.query_one("#diff-view", CodeView).line_count == 3000
            assert ch.text_of(app, "#diff-cap") == "Showing the first 3000 of 6004 lines."

    ch.run(scenario)


def test_the_route_helper_builds_the_path_the_fake_link_serves():
    assert route("/diff", support.GLOBEX, repo=ch.API) == ch.route_diff(support.GLOBEX, ch.API)
