from __future__ import annotations

import asyncio

import _changes_support as ch
import _tui_support as support
import pytest
from textual.widgets import Input, OptionList

from groom import state
from groom.tui.widgets.repo import RepoPicker


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


def options(app) -> list[str]:
    listing = app.screen.query_one(OptionList)
    return [str(listing.get_option_at_index(i).prompt) for i in range(listing.option_count)]


async def open_picker(app, pilot) -> None:
    await pilot.press("p")
    await support.until(lambda: isinstance(app.screen, RepoPicker))
    await support.until(lambda: options(app))


def test_p_opens_the_picker_and_it_lists_state_type_and_label():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await open_picker(app, pilot)
            rows = options(app)
            assert len(rows) == 3
            assert rows[0].split() == ["running", "author", "author-globex/api-service"]
            assert rows[2].split() == ["finished", "coder", "coder-web-app/web-app"]
            assert app.screen.query_one(Input).has_focus

    ch.run(scenario)


def test_p_does_nothing_on_the_gate_and_trail_tabs():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("t", "p")
            await pilot.pause()
            assert not isinstance(app.screen, RepoPicker)
            assert link.gets == []

    ch.run(scenario)


def test_typing_filters_the_list_and_enter_picks_the_highlighted_row():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("f")
            await support.until(lambda: ch.tree_labels(app))
            await open_picker(app, pilot)
            await pilot.press(*"WEB")
            assert [row.split()[-1] for row in options(app)] == ["author-globex/web-app", "coder-web-app/web-app"]
            await pilot.press("enter")
            await support.until(lambda: not isinstance(app.screen, RepoPicker))
            await support.until(lambda: ch.route_files(support.GLOBEX, ch.WEB) in link.gets)
            assert app.store.repo == {"container": support.GLOBEX, "repo": ch.WEB, "label": "author-globex/web-app"}
            await support.until(lambda: ch.tree_labels(app) == ["index.html"])
            assert "author-globex/web-app" in ch.text_of(app, "#files-repo")

    ch.run(scenario)


def test_the_choice_is_shared_so_d_after_it_fetches_the_diff_of_that_repo():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("f")
            await support.until(lambda: ch.tree_labels(app))
            await open_picker(app, pilot)
            await pilot.press(*"web", "enter")
            await support.until(lambda: ch.tree_labels(app) == ["index.html"])
            await pilot.press("d")
            await support.until(lambda: ch.route_diff(support.GLOBEX, ch.WEB) in link.gets)
            await support.until(lambda: ch.diff_rows(app) == ["README.md  +2 -0"])
            assert ch.route_diff(support.GLOBEX, ch.API) not in link.gets
            assert link.gets.count("/repos") == 2

    ch.run(scenario)


def test_the_arrow_keys_move_the_highlight_while_the_input_keeps_focus():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await open_picker(app, pilot)
            listing = app.screen.query_one(OptionList)
            assert listing.highlighted == 0
            await pilot.press("down", "down")
            assert listing.highlighted == 2
            await pilot.press("down")
            assert listing.highlighted == 2
            await pilot.press("up")
            assert listing.highlighted == 1
            assert app.screen.query_one(Input).has_focus
            await pilot.press("enter")
            await support.until(lambda: ch.route_diff(support.GLOBEX, ch.WEB) in link.gets)

    ch.run(scenario)


def test_escape_leaves_the_repository_unchanged():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            before = app.store.repo
            asked = list(link.gets)
            await open_picker(app, pilot)
            await pilot.press("down", "escape")
            await support.until(lambda: not isinstance(app.screen, RepoPicker))
            await pilot.pause()
            assert app.store.repo == before
            assert link.gets == [*asked, "/repos"]
            assert ch.diff_rows(app) == ["src/app.py  +1 -1", "README.md  +2 -0"]

    ch.run(scenario)


def test_the_picker_states_nothing_available_and_a_failed_load():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            link.list_replies["/repos"] = []
            await pilot.press("p")
            await support.until(lambda: isinstance(app.screen, RepoPicker))
            await support.until(lambda: ch.text_of(app.screen, "#repo-note") == "No repositories available.")
            await pilot.press("escape")
            del link.list_replies["/repos"]
            await pilot.press("p")
            await support.until(lambda: isinstance(app.screen, RepoPicker))
            await support.until(lambda: ch.text_of(app.screen, "#repo-note").startswith("Could not load repositories: "))
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RepoPicker)

    ch.run(scenario)


def test_the_picker_shows_loading_until_the_repos_arrive():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            link.holds["/repos"] = held = asyncio.Event()
            await pilot.press("p")
            await support.until(lambda: isinstance(app.screen, RepoPicker))
            await support.until(lambda: link.gets.count("/repos") == 2)
            assert ch.text_of(app.screen, "#repo-note") == "Loading…"
            held.set()
            await support.until(lambda: options(app))
            assert ch.text_of(app.screen, "#repo-note") == ""

    ch.run(scenario)


def test_opening_another_run_resets_the_repository_to_that_runs_container():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[ch.route_diff(support.WEBAPP, ch.WEB)] = {"diff": ch.MODIFY}
        link.get_replies[ch.route_diff(support.ACME, "")] = {"diff": ch.ADD}
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await open_picker(app, pilot)
            await pilot.press(*"coder", "enter")
            await support.until(lambda: ch.route_diff(support.WEBAPP, ch.WEB) in link.gets)
            assert app.store.repo is not None
            assert app.store.repo["container"] == support.WEBAPP
            await app.open_run(support.ACME)
            link.push(support.history_frame(support.ACME, [support.log_row(1.0, "x")]))
            await support.until(lambda: app.store.detail is not None)
            await pilot.pause()
            assert app.store.repo is None
            assert ch.diff_rows(app) == []
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            assert app.store.repo is not None
            assert app.store.repo == {"container": support.ACME, "repo": "", "label": "coder-acme"}
            assert link.gets[-1] == ch.route_diff(support.ACME, "")

    ch.run(scenario)


def test_a_run_with_no_repo_on_its_volume_falls_back_to_its_own_container():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        link.get_replies[f"/diff/{support.ACME}?repo="] = {"diff": ch.ADD}
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link, support.ACME)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            assert app.store.repo == {"container": support.ACME, "repo": "", "label": "coder-acme"}
            assert "coder-acme" in ch.text_of(app, "#diff-repo")

    ch.run(scenario)


def test_opening_the_run_that_is_already_open_keeps_the_chosen_repository():
    async def scenario() -> None:
        link = support.FakeLink()
        ch.serve(link)
        async with ch.booted(link) as (app, pilot):
            await ch.open_run(app, pilot, link)
            await pilot.press("d")
            await support.until(lambda: ch.diff_rows(app))
            await open_picker(app, pilot)
            await pilot.press(*"web", "enter")
            await support.until(lambda: ch.route_diff(support.GLOBEX, ch.WEB) in link.gets)
            chosen = app.store.repo
            await app.open_run(support.GLOBEX)
            assert app.store.repo == chosen
            link.push(support.history_frame(support.GLOBEX, []))
            await support.until(lambda: app.store.detail is not None)
            await pilot.press("t", "d")
            await support.until(lambda: link.gets.count(ch.route_diff(support.GLOBEX, ch.WEB)) == 2)
            assert ch.route_diff(support.GLOBEX, ch.API) in link.gets
            assert link.gets.count(ch.route_diff(support.GLOBEX, ch.API)) == 1

    ch.run(scenario)
