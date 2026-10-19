from __future__ import annotations

import time

import _attend_support as at
import _attend_ui as ui
import _tui_support as support
import _trail_support as tr
import pytest
from textual.widgets import OptionList

from groom import state
from groom.models import WorkflowState
from groom.tui.route import route
from groom.tui.screens.attend import AttendScreen, StopConfirm
from groom.tui.screens.settings import SettingsScreen


@pytest.fixture(autouse=True)
def _groom(tmp_path, monkeypatch):
    at.isolate(tmp_path, monkeypatch, "headless")
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    support.seed()
    yield
    state.WORKFLOWS.clear()
    at.release()
    monkeypatch.undo()
    time.tzset()


async def press_stop(app, pilot, screen, job_id: str) -> None:
    ui.listing(screen).highlighted = ui.ids(screen).index(job_id)
    await pilot.press("x")


def test_x_on_a_running_row_asks_and_yes_posts_the_stop_then_refetches():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        link.post_replies[route(at.SESSIONS, "j-live") + "/stop"] = {"ok": True}
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await press_stop(app, pilot, screen, "j-live")
            await support.until(lambda: isinstance(app.screen, StopConfirm))
            assert "Stop the attendant on okf-builder? The run comes back to your terminal." in at.screen_text(app.screen)
            assert link.posts == []
            await pilot.press("y")
            await support.until(lambda: link.posts)
            assert link.post_log == [(route(at.SESSIONS, "j-live") + "/stop", None)]
            await support.until(lambda: link.gets.count(at.SESSIONS) == 2)
            assert app.screen is screen
            assert not app._notifications

    tr.run(scenario)


@pytest.mark.parametrize("key", ["n", "escape"])
def test_no_or_escape_posts_nothing(key):
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await press_stop(app, pilot, screen, "j-live")
            await support.until(lambda: isinstance(app.screen, StopConfirm))
            await pilot.press(key)
            await support.until(lambda: app.screen is screen)
            await pilot.pause()
            assert link.posts == []
            assert link.gets == [at.SESSIONS]

    tr.run(scenario)


def test_x_on_a_completed_row_does_nothing():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await press_stop(app, pilot, screen, "j-done")
            await pilot.pause()
            assert app.screen is screen

    tr.run(scenario)


def test_a_stop_that_finds_the_attendant_gone_says_so_and_refetches():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        link.post_replies[route(at.SESSIONS, "j-live") + "/stop"] = {"ok": False}
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await press_stop(app, pilot, screen, "j-live")
            await support.until(lambda: isinstance(app.screen, StopConfirm))
            await pilot.press("y")
            await support.until(lambda: any(n.message == "That attendant was already gone." for n in app._notifications))
            await support.until(lambda: link.gets.count(at.SESSIONS) == 2)

    tr.run(scenario)


def test_a_stop_groom_does_not_answer_toasts_the_reason_and_refetches():
    from groom.tui.link import LinkError

    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        link.post_replies[route(at.SESSIONS, "j-live") + "/stop"] = LinkError("HTTP 500: store is locked")
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await press_stop(app, pilot, screen, "j-live")
            await support.until(lambda: isinstance(app.screen, StopConfirm))
            await pilot.press("y")
            await support.until(lambda: app._notifications)
            assert [n.message for n in app._notifications] == ["groom did not answer the stop: HTTP 500: store is locked"]
            await support.until(lambda: link.gets.count(at.SESSIONS) == 2)

    tr.run(scenario)


def test_the_run_detail_names_its_attendant_and_a_opens_that_session():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.ACME, [])
            line = at.static(app.main, "#attendant")
            assert line == "an attendant is on this run · credential wall  (A)"
            await pilot.press("A")
            await support.until(lambda: isinstance(app.screen, AttendScreen))
            await support.until(lambda: route(at.SESSIONS, "s-live") in link.gets)
            await support.until(lambda: "working" in at.screen_text(app.screen))
            await support.until(lambda: ui.highlighted(app.screen) == "j-live")

    tr.run(scenario)


def test_a_finished_attendant_reads_last_attendant_and_a_run_without_one_shows_no_line():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, [])
            line = at.static(app.main, "#attendant")
            assert line == "last attendant · stuck on a gate  (A)"
            await app.open_run(support.WEBAPP)
            link.push(support.history_frame(support.WEBAPP, []))
            await support.until(lambda: app.store.detail is not None)
            assert at.static(app.main, "#attendant") == "last attendant  (A)"
            at.release()
            state.WORKFLOWS[support.WEBAPP].run_id = "run-none"
            link.push(support.state_frame())
            await support.until(lambda: not at.static(app.main, "#attendant"))

    tr.run(scenario)


def test_a_toggles_nothing_when_already_there_and_s_switches_screens():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        link.get_replies[at.SETTINGS] = {"mode": "headless", "cli": "claude", "sources": {"mode": "config"}}
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await pilot.press("A")
            await pilot.pause()
            assert app.screen is screen
            assert len(app.screen_stack) == 2
            await pilot.press("S")
            await support.until(lambda: isinstance(app.screen, SettingsScreen))
            assert len(app.screen_stack) == 2
            await pilot.press("S")
            await pilot.press("A")
            await support.until(lambda: isinstance(app.screen, AttendScreen))
            assert len(app.screen_stack) == 2
            await pilot.press("escape")
            await support.until(lambda: app.screen is app.main)
            assert len(app.screen_stack) == 1

    tr.run(scenario)


def test_main_keys_do_nothing_on_the_attendant_screen():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            before = app.main.query_one("#runs", OptionList).highlighted
            await pilot.press("r", "d", "f")
            await pilot.pause()
            assert link.posts == []
            assert app.screen is screen
            assert app.main.query_one("#runs", OptionList).highlighted == before

    tr.run(scenario)


def test_state_and_run_frames_reach_the_run_list_while_a_screen_is_open():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            state.upsert_workflow(
                "initech12345", name="coder-initech", workflow_type="coder", repo_name="initech",
                current_node="plan", run_id="run-new", state=WorkflowState.RUNNING,
            )
            link.push(support.state_frame())
            state.WORKFLOWS["initech12345"].current_node = "review"
            link.push(support.run_frame("initech12345"))
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 4)
            assert app.screen is screen
            await pilot.press("escape")
            await support.until(lambda: app.screen is app.main)
            runs = at.prompts(app.main.query_one("#runs", OptionList))
            assert len(runs) == 4
            assert any("coder-initech" in row and "review" in row for row in runs)
            assert "4 runs" in at.widget_text(app.main.query_one("#status"))

    tr.run(scenario)
