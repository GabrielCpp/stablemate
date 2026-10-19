from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager

import _tui_support as support
import pytest
from textual.command import CommandList, CommandPalette, DiscoveryHit, Hit
from textual.pilot import Pilot
from textual.widgets import OptionList

from groom import state
from groom.tui.app import GroomTui
from groom.tui.widgets.palette import FleetProvider


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


async def _loaded(link: support.FakeLink, app: GroomTui) -> None:
    link.push(support.state_frame())
    await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)


def _palette(app: GroomTui) -> CommandPalette:
    screen = app.screen
    assert isinstance(screen, CommandPalette)
    return screen


def _shown(app: GroomTui) -> list[str]:
    listing = _palette(app).query_one(CommandList)
    return [str(listing.get_option_at_index(i).prompt) for i in range(listing.option_count)]


async def _hits(app: GroomTui, query: str) -> list[Hit]:
    provider = FleetProvider(app.screen, None)
    return [hit async for hit in provider.search(query) if isinstance(hit, Hit)]


def test_ctrl_p_finds_a_run_the_list_filter_hides_and_choosing_it_sends_watch():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("/", "g", "l", "o", "b")
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 1)
            await pilot.press("enter")
            await pilot.press("ctrl+p")
            await support.until(lambda: isinstance(app.screen, CommandPalette))
            await pilot.press(*"acme")
            await support.until(lambda: any("coder-acme" in line or "acme #" in line for line in _shown(app)))
            await pilot.press("enter")
            await support.until(lambda: link.sent)
            assert link.sent[-1] == {"cmd": "watch", "run_id": support.ACME}
            assert app.store.selected == support.ACME
            assert app.store.query == "glob"

    _run(scenario)


def test_a_run_hidden_by_the_filter_is_found_by_a_haystack_substring_the_row_does_not_show():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("/", "z", "z", "z")
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 0)
            hits = await _hits(app, "await_oper")
            assert [hit.text for hit in hits if hit.text and "acme" in hit.text] != []
            assert all(hit.score > 0 for hit in hits)

    _run(scenario)


def test_a_hit_shows_the_state_word_repo_row_id_doing_and_the_hint():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, _pilot):
            await _loaded(link, app)
            blocked = next(hit for hit in await _hits(app, "coder-acme") if hit.help == "gate")
            assert blocked.text is not None
            assert blocked.text.startswith("blocked")
            assert "acme #" in blocked.text
            running = next(hit for hit in await _hits(app, "author-globex") if hit.text and "globex" in hit.text)
            assert running.help == "unknown"
            assert running.text is not None
            assert running.text.startswith("running")

    _run(scenario)


def test_the_palette_offers_the_tabs_and_rescan():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            provider = FleetProvider(app.screen, None)
            names = [hit.text async for hit in provider.discover() if isinstance(hit, DiscoveryHit)]
            for expected in ("Show Gate tab", "Show Trail tab", "Show Diff tab", "Show Files tab", "Rescan"):
                assert expected in names
            await pilot.press("ctrl+p")
            await support.until(lambda: isinstance(app.screen, CommandPalette))
            await pilot.press(*"rescan")
            await support.until(lambda: any("Rescan" in line for line in _shown(app)))
            await pilot.press("enter")
            await support.until(lambda: link.posts)
            assert link.posts == ["/refresh"]

    _run(scenario)


def test_a_tab_command_switches_the_open_runs_tab():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _loaded(link, app)
            await pilot.press("enter")
            await support.until(lambda: link.sent)
            link.push(support.detail_frame(support.ACME))
            await support.until(lambda: app.store.detail is not None)
            await pilot.press("ctrl+p")
            await support.until(lambda: isinstance(app.screen, CommandPalette))
            await pilot.press(*"show trail")
            await support.until(lambda: any("Show Trail tab" in line for line in _shown(app)))
            await pilot.press("enter")
            await support.until(lambda: app.pane.tab == "trail")

    _run(scenario)


def test_a_hostile_run_name_reaches_the_palette_without_control_bytes():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, _pilot):
            wf = state.WORKFLOWS[support.GLOBEX]
            wf.repo_name = "evil\x1b]52;c;ZXZpbA==\x07-repo\x1b[2J\x9b31m"
            wf.activity = "doing\x1b[31m\x07 bad\x00"
            link.push(support.state_frame())
            await support.until(lambda: any("evil" in str(row.get("repo")) for row in app.store.runs))
            hits = await _hits(app, "evil")
            provider = FleetProvider(app.screen, None)
            discovered = [hit async for hit in provider.discover() if isinstance(hit, DiscoveryHit)]
            shown = [hit.text or "" for hit in [*hits, *discovered]] + [str(hit.prompt) for hit in [*hits, *discovered]]
            assert any("evil" in text for text in shown)
            for text in shown:
                assert not any(ch in text for ch in "\x1b\x07\x00\x9b"), repr(text)

    _run(scenario)
