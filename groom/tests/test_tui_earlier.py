from __future__ import annotations

import _attend_support as at
import _attend_ui as ui
import _trail_support as tr
import _tui_support as support
import pytest
from textual.containers import Vertical

from groom import state
from groom.tui.widgets.lines import ENTRY_PAGE, EarlierEntries, tail_entries


@pytest.fixture(autouse=True)
def _groom(tmp_path, monkeypatch):
    at.isolate(tmp_path, monkeypatch, "session")
    support.seed()
    yield
    state.WORKFLOWS.clear()
    at.release()


def keyed(count: int) -> list[tuple[str, dict]]:
    return [(f"#{n}", {"n": n}) for n in range(count)]


def test_tail_entries_returns_the_hidden_count_and_the_newest_items_with_their_keys():
    hidden, shown = tail_entries(keyed(100), 40)
    assert hidden == 60
    assert [key for key, _ in shown] == [f"#{n}" for n in range(60, 100)]
    assert tail_entries(keyed(40), 40) == (0, keyed(40))
    assert tail_entries(keyed(3), 40) == (0, keyed(3))
    assert tail_entries([], 40) == (0, [])


async def open_transcript(app, pilot, link, count: int, rows: int = 1):
    at.begin("j-1", "run-blocked", session="s-1", started_at=at.T0)
    at.write_transcript("s-1", [at.turn("assistant", [{"type": "text", "text": f"Entry {n}"}]) for n in range(count)])
    await at.serve_sessions(link)
    await at.serve_session(link, "s-1")
    screen = await ui.open_attend(app, pilot, link, rows=rows)
    await ui.read(pilot, screen, "j-1", link, "s-1")
    return screen


def shown(screen) -> list[str]:
    body = screen.query_one("#attend-body", Vertical)
    return [at.widget_text(child) for child in body.children if not isinstance(child, EarlierEntries)]


def label_of(found) -> str:
    assert found is not None
    return str(found.label)


def button(screen):
    found = screen.query(EarlierEntries)
    return found.first() if found else None


async def settle(pilot, screen, count: int) -> None:
    await support.until(lambda: len(shown(screen)) == count)
    await pilot.pause()


def test_a_long_transcript_opens_on_its_newest_entries_with_a_button_for_the_rest():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            screen = await open_transcript(app, pilot, link, 100)
            await settle(pilot, screen, ENTRY_PAGE)
            texts = shown(screen)
            assert "Entry 99" in texts[-1]
            assert "Entry 60" in texts[0]
            first = screen.query_one("#attend-body", Vertical).children[0]
            assert isinstance(first, EarlierEntries)
            assert str(first.label) == "Show 40 earlier entries (60 hidden)"

    tr.run(scenario)


def test_there_is_no_button_at_or_under_the_page_size():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            screen = await open_transcript(app, pilot, link, ENTRY_PAGE)
            await settle(pilot, screen, ENTRY_PAGE)
            assert button(screen) is None

    tr.run(scenario)


def test_pressing_the_button_shows_a_page_more_and_the_last_page_drops_it():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            screen = await open_transcript(app, pilot, link, 100)
            await settle(pilot, screen, 40)
            await pilot.click(EarlierEntries)
            await settle(pilot, screen, 80)
            assert label_of(button(screen)) == "Show 20 earlier entries (20 hidden)"
            assert "Entry 20" in shown(screen)[0]
            await pilot.click(EarlierEntries)
            await settle(pilot, screen, 100)
            assert button(screen) is None

    tr.run(scenario)


def test_e_shows_earlier_entries_like_the_button():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            screen = await open_transcript(app, pilot, link, 100)
            await settle(pilot, screen, 40)
            await pilot.press("e")
            await settle(pilot, screen, 80)
            await pilot.press("e")
            await settle(pilot, screen, 100)
            await pilot.press("e")
            await pilot.pause()
            assert len(shown(screen)) == 100

    tr.run(scenario)


def test_opening_another_session_resets_the_window():
    async def scenario() -> None:
        link = support.FakeLink()
        at.begin("j-2", "run-done", session="s-2", started_at=at.T0 + 5)
        at.write_transcript("s-2", [at.turn("assistant", [{"type": "text", "text": f"Other {n}"}]) for n in range(100)])
        async with tr.booted(link) as (app, pilot):
            screen = await open_transcript(app, pilot, link, 100, rows=2)
            await at.serve_session(link, "s-2")
            await settle(pilot, screen, 40)
            await pilot.press("e")
            await settle(pilot, screen, 80)
            await ui.read(pilot, screen, "j-2", link, "s-2")
            await settle(pilot, screen, 40)
            assert "Other 99" in shown(screen)[-1]
            await ui.read(pilot, screen, "j-1", link, "s-1")
            await settle(pilot, screen, 40)

    tr.run(scenario)


def live_rows(count: int) -> list[dict]:
    return [
        support.transcript_row(200.0 + n, support.tool_update(f"tool{n}", ""), tr.LIVE, "review") for n in range(count)
    ]


def turn_texts(app) -> list[str]:
    group = tr.turns(app)[tr.LIVE]
    return [at.widget_text(child) for child in group.query(".entry-tool")]


def turn_button(app):
    found = tr.turns(app)[tr.LIVE].query(EarlierEntries)
    return found.first() if found else None


def test_a_running_turn_keeps_its_newest_entries_as_it_grows_and_remembers_its_window():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, live_rows(100))
            assert len(turn_texts(app)) == ENTRY_PAGE
            assert "tool99" in turn_texts(app)[-1]
            assert label_of(turn_button(app)) == "Show 40 earlier entries (60 hidden)"
            await tr.push_detail(app, pilot, link, support.GLOBEX, live_rows(101))
            await support.until(lambda: "tool100" in turn_texts(app)[-1])
            assert len(turn_texts(app)) == ENTRY_PAGE
            assert label_of(turn_button(app)) == "Show 40 earlier entries (61 hidden)"
            await pilot.click(EarlierEntries)
            await support.until(lambda: len(turn_texts(app)) == 80)
            await tr.push_detail(app, pilot, link, support.GLOBEX, live_rows(102))
            await support.until(lambda: "tool101" in turn_texts(app)[-1])
            assert len(turn_texts(app)) == 80
            assert label_of(turn_button(app)) == "Show 22 earlier entries (22 hidden)"

    tr.run(scenario)


def test_a_turn_at_the_page_size_has_no_button():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, live_rows(ENTRY_PAGE))
            assert turn_button(app) is None

    tr.run(scenario)
