from __future__ import annotations

import re
import threading

import _changes_support as ch
import _tui_support as support
import pytest
from textual import events
from textual.widgets import Tree

from groom import state
from groom.tui.widgets import code as code_module
from groom.tui.widgets.code import CodeView

CONTROLS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
BIG = "".join(f"x{n} = {n}\n" for n in range(2500))
APP_PY = ch.route_file(support.GLOBEX, ch.API, "src/app.py")


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


async def open_big(app, pilot, link, content: str = BIG) -> CodeView:
    link.get_replies[APP_PY] = {"path": "src/app.py", "content": content, "lang": "python"}
    await ch.open_run(app, pilot, link)
    await pilot.press("f")
    await support.until(lambda: ch.tree_labels(app))
    app.query_one("#files-tree", Tree).select_node(ch.tree_leaf(app, "src", "app.py"))
    view = app.query_one("#file-view", CodeView)
    await support.until(lambda: view.line_count > 0)
    await pilot.pause()
    return view


def rendered(view: CodeView) -> str:
    return "\n".join(view.render_line(y).text for y in range(view.size.height))


def test_only_the_visible_lines_are_rendered_until_the_view_scrolls(monkeypatch):
    async def scenario() -> None:
        rows: list[int] = []
        original = CodeView.strip_for

        def spy(self, row):
            rows.append(row)
            return original(self, row)

        monkeypatch.setattr(CodeView, "strip_for", spy)
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            view = await open_big(app, pilot, link)
            assert view.line_count == 2500
            assert 0 < view.size.height < 100
            shown = rendered(view)
            assert "x0 = 0" in shown
            assert "x2499" not in shown
            assert max(rows) < view.size.height
            view.scroll_to(y=2400, animate=False, immediate=True)
            await pilot.pause()
            assert "x2400 = 2400" in view.render_line(0).text
            assert max(rows) >= 2400
            assert len(set(rows)) < 2500 // 10

    ch.run(scenario)


def test_the_arrow_page_and_end_keys_scroll_a_focused_view():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            view = await open_big(app, pilot, link)
            view.focus()
            await pilot.pause()
            assert view.scroll_offset.y == 0
            await pilot.press("down")
            await pilot.pause()
            assert view.scroll_offset.y == 1
            await pilot.press("pagedown")
            await pilot.pause()
            assert view.scroll_offset.y > view.size.height - 2
            await pilot.press("end")
            await pilot.pause()
            assert view.scroll_offset.y == 2500 - view.size.height
            assert "x2499 = 2499" in rendered(view)
            await pilot.press("home")
            await pilot.pause()
            assert view.scroll_offset.y == 0

    ch.run(scenario)


def test_the_mouse_wheel_scrolls_the_view():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            view = await open_big(app, pilot, link)
            view.post_message(events.MouseScrollDown(view, 1, 1, 0, 0, 0, False, False, False))
            await pilot.pause()
            assert view.scroll_offset.y > 0

    ch.run(scenario)


def test_a_long_line_scrolls_sideways_instead_of_wrapping():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            view = await open_big(app, pilot, link, "short\n" + "w" * 300 + "tail\n")
            assert view.virtual_size.width == 304
            assert "tail" not in view.render_line(1).text
            view.scroll_to(x=250, animate=False, immediate=True)
            await pilot.pause()
            assert view.render_line(1).text.rstrip().endswith("tail")

    ch.run(scenario)


def test_the_cleaned_content_stays_cleaned_in_every_rendered_line():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            view = await open_big(app, pilot, link, "top\x1b[2Jbottom\x1b]52;c;aGk=\x07\nnext\x9b31m\n")
            shown = rendered(view)
            assert "topbottom" in shown
            assert not CONTROLS.search(shown)

    ch.run(scenario)


def test_the_highlight_runs_off_the_event_loop(monkeypatch):
    async def scenario() -> None:
        threads: list[str] = []
        original = code_module.highlight_lines

        def spy(code: str, lexer: str):
            threads.append(threading.current_thread().name)
            return original(code, lexer)

        monkeypatch.setattr("groom.tui.widgets.files.highlight_lines", spy)
        monkeypatch.setattr("groom.tui.widgets.diff.highlight_lines", spy)
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await open_big(app, pilot, link, "x = 1\n")
            await pilot.press("t", "d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("down")
            await support.until(lambda: ch.code_of(app, "#diff-view"))
            assert len(threads) == 2
            assert threading.main_thread().name not in threads

    ch.run(scenario)


def test_loading_shows_while_the_highlight_is_pending(monkeypatch):
    async def scenario() -> None:
        release = threading.Event()
        original = code_module.highlight_lines

        def held(code: str, lexer: str):
            release.wait(5)
            return original(code, lexer)

        monkeypatch.setattr("groom.tui.widgets.diff.highlight_lines", held)
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("down")
            assert ch.text_of(app, "#diff-view-note") == "Loading…"
            assert not app.query_one("#diff-view", CodeView).display
            release.set()
            await support.until(lambda: ch.code_of(app, "#diff-view"))
            assert ch.text_of(app, "#diff-view-note") == ""

    ch.run(scenario)


def test_arrowing_past_a_file_drops_its_stale_highlight(monkeypatch):
    async def scenario() -> None:
        release = threading.Event()
        original = code_module.highlight_lines

        def slow(code: str, lexer: str):
            if "src/app.py" in code:
                release.wait(5)
            return original(code, lexer)

        monkeypatch.setattr("groom.tui.widgets.diff.highlight_lines", slow)
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await pilot.press("down", "down")
            await support.until(lambda: "+# Title" in ch.code_of(app, "#diff-view"))
            release.set()
            await pilot.pause()
            assert "+# Title" in ch.code_of(app, "#diff-view")
            assert "new line" not in ch.code_of(app, "#diff-view")

    ch.run(scenario)
