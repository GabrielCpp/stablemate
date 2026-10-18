from __future__ import annotations

import asyncio
import re

import _changes_support as ch
import _tui_support as support
import pytest
from textual.widgets import Tree

from groom import state
from groom.tui.route import route
from groom.tui.widgets.code import CodeView

CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
APP_PY = ch.route_file(support.GLOBEX, ch.API, "src/app.py")
README = ch.route_file(support.GLOBEX, ch.API, "README.md")


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


async def open_files(app, pilot, link) -> None:
    await ch.open_run(app, pilot, link)
    await pilot.press("f")
    await support.until(lambda: ch.tree_labels(app))


def test_f_fetches_the_file_list_and_builds_a_tree_with_directories_first():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            assert link.gets == ["/repos", ch.route_files(support.GLOBEX, ch.API)]
            assert app.pane.tab == "files"
            assert ch.files_tab(app).display
            assert app.query_one("#files-tree", Tree).has_focus
            assert ch.tree_labels(app) == ["src", "README.md"]
            assert ch.text_of(app, "#file-head") == ""
            assert ch.text_of(app, "#file-note") == "Select a file to view it."
            assert "author-globex/api-service" in ch.text_of(app, "#files-repo")

    ch.run(scenario)


def test_selecting_a_leaf_fetches_the_file_and_shows_its_content():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            app.query_one("#files-tree", Tree).select_node(ch.tree_leaf(app, "src", "app.py"))
            await support.until(lambda: ch.code_of(app, "#file-view") == "print('a')")
            assert APP_PY in link.gets
            assert app.query_one("#file-view", CodeView).display
            assert ch.text_of(app, "#file-note") == ""
            assert ch.text_of(app, "#file-head") == "src/app.py"

    ch.run(scenario)


def test_the_keyboard_walks_the_tree_and_opens_a_file():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            await pilot.press("down", "down", "enter")
            await support.until(lambda: README in link.gets)
            await support.until(lambda: ch.text_of(app, "#file-head") == "README.md")

    ch.run(scenario)


def test_a_late_reply_for_an_earlier_file_never_replaces_the_later_one():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.holds[README] = release = asyncio.Event()
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            tree = app.query_one("#files-tree", Tree)
            tree.select_node(ch.tree_leaf(app, "README.md"))
            await support.until(lambda: README in link.gets)
            assert ch.text_of(app, "#file-note") == "Loading…"
            tree.select_node(ch.tree_leaf(app, "src", "app.py"))
            await support.until(lambda: ch.text_of(app, "#file-head") == "src/app.py" and ch.code_of(app, "#file-view") == "print('a')")
            release.set()
            await pilot.pause()
            await asyncio.sleep(0.1)
            assert ch.text_of(app, "#file-head") == "src/app.py"
            assert ch.code_of(app, "#file-view") == "print('a')"

    ch.run(scenario)


def test_an_empty_file_says_so_and_a_failed_file_says_why():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[README] = {"path": "README.md", "content": "", "lang": "markdown"}
        del link.get_replies[APP_PY]
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            tree = app.query_one("#files-tree", Tree)
            tree.select_node(ch.tree_leaf(app, "README.md"))
            await support.until(lambda: ch.text_of(app, "#file-note") == "Empty or binary file.")
            tree.select_node(ch.tree_leaf(app, "src", "app.py"))
            await support.until(lambda: ch.text_of(app, "#file-note").startswith("Could not load the file: "))

    ch.run(scenario)


def test_the_file_list_states_empty_and_failed():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[ch.route_files(support.GLOBEX, ch.API)] = {"paths": []}
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("f")
            await support.until(lambda: ch.text_of(app, "#files-note") == "No files.")
            del link.get_replies[ch.route_files(support.GLOBEX, ch.API)]
            await pilot.press("t", "f")
            await support.until(lambda: ch.text_of(app, "#files-note").startswith("Could not load files: "))

    ch.run(scenario)


def test_the_loading_note_shows_while_the_file_list_is_in_flight():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        route_path = ch.route_files(support.GLOBEX, ch.API)
        link.holds[route_path] = held = asyncio.Event()
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("f")
            await support.until(lambda: route_path in link.gets)
            assert ch.text_of(app, "#files-note") == "Loading files…"
            held.set()
            await support.until(lambda: ch.tree_labels(app))

    ch.run(scenario)


def test_a_detail_push_leaves_the_tree_and_the_open_file_alone():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            app.query_one("#files-tree", Tree).select_node(ch.tree_leaf(app, "src", "app.py"))
            await support.until(lambda: ch.code_of(app, "#file-view") == "print('a')")
            asked = list(link.gets)
            cursor = app.query_one("#files-tree", Tree).cursor_line
            seen = app.store.detail
            link.push(support.history_frame(support.GLOBEX, [support.log_row(100.0, "tick")]))
            await support.until(lambda: app.store.detail is not seen)
            await pilot.pause()
            assert link.gets == asked
            assert app.query_one("#files-tree", Tree).cursor_line == cursor
            assert ch.code_of(app, "#file-view") == "print('a')"

    ch.run(scenario)


def test_an_unknown_server_language_falls_back_to_a_guessed_lexer():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[APP_PY] = {"path": "src/app.py", "content": "x = 1\n", "lang": "no-such-language"}
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            app.query_one("#files-tree", Tree).select_node(ch.tree_leaf(app, "src", "app.py"))
            await support.until(lambda: ch.code_of(app, "#file-view") == "x = 1")
            colours = {span.style for line in app.query_one("#file-view", CodeView).lines for span in line.spans}
            assert colours

    ch.run(scenario)


def test_a_hostile_path_and_file_reach_the_widgets_without_control_bytes():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        evil = "bad\x9b31m.txt"
        link.get_replies[ch.route_files(support.GLOBEX, ch.API)] = {"paths": [evil]}
        link.get_replies[route("/file", support.GLOBEX, repo=ch.API, path=evil)] = {
            "path": evil, "content": "top\x1b[2Jbottom\x1b]52;c;aGk=\x07\n", "lang": "",
        }
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            assert ch.tree_labels(app) == ["bad.txt"]
            app.query_one("#files-tree", Tree).select_node(ch.tree_leaf(app, "bad.txt"))
            await support.until(lambda: ch.code_of(app, "#file-view"))
            shown = ch.code_of(app, "#file-view") + ch.text_of(app, "#file-head") + "".join(ch.tree_labels(app))
            assert "topbottom" in shown
            assert not CONTROLS.search(shown)
            assert "52;c" not in shown

    ch.run(scenario)


def test_a_long_file_shows_five_thousand_lines_and_a_note():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[APP_PY] = {
            "path": "src/app.py", "content": "".join(f"x{n} = {n}\n" for n in range(6000)), "lang": "python",
        }
        async with ch.booted(link) as (app, pilot):
            await open_files(app, pilot, link)
            app.query_one("#files-tree", Tree).select_node(ch.tree_leaf(app, "src", "app.py"))
            await support.until(lambda: ch.code_of(app, "#file-view"))
            assert app.query_one("#file-view", CodeView).line_count == 3000
            assert ch.text_of(app, "#file-cap") == "Showing the first 3000 of 6000 lines."

    ch.run(scenario)
