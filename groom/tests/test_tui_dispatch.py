from __future__ import annotations

import asyncio
import time

import _attend_support as at
import _dispatch_support as dp
import _tui_support as support
import pytest
from textual.widgets import OptionList

from groom import state
from groom.tui.screens import dispatch as screen_module
from groom.tui.screens.attend import AttendScreen
from groom.tui.screens.settings import SettingsScreen


@pytest.fixture(autouse=True)
def _groom(tmp_path, monkeypatch):
    dp.isolate(tmp_path, monkeypatch)
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    support.seed()
    yield
    state.WORKFLOWS.clear()
    dp.release()
    monkeypatch.undo()
    time.tzset()


async def stocked() -> support.FakeLink:
    link = support.FakeLink()
    dp.stock_items()
    await dp.serve(link)
    return link


def test_the_queue_rows_name_the_occupancy_and_the_command():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            assert at.prompts(dp.queue_list(screen)) == [
                "plans  1/2 running\nworkhorse-plan-runner",
                "reviews  1/1 running\nworkhorse-review-runner",
            ]
            assert dp.note(screen, "queues") == ""

    dp.run(scenario)


def test_the_screen_says_loading_until_the_queues_answer():
    async def scenario() -> None:
        link = await stocked()
        link.holds[dp.QUEUES] = asyncio.Event()
        async with dp.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("D")
            await support.until(lambda: isinstance(app.screen, screen_module.DispatchScreen))
            await support.until(lambda: dp.QUEUES in link.gets)
            assert dp.note(app.screen, "queues") == "Loading queues…"
            assert dp.note(app.screen, "items") == "Select a queue to see its items."
            assert dp.detail(app.screen) == "Select an item to see its parameters."
            link.holds[dp.QUEUES].set()
            await support.until(lambda: dp.queue_list(app.screen).option_count == 2)
            assert dp.note(app.screen, "queues") == ""

    dp.run(scenario)


def test_no_configured_queue_says_how_to_add_one(tmp_path):
    async def scenario() -> None:
        dp.write_config(tmp_path, {})
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("D")
            await support.until(lambda: dp.QUEUES in link.gets)
            await support.until(lambda: dp.note(app.screen, "queues"))
            assert dp.note(app.screen, "queues") == (
                "No dispatch queues configured. Add a [groom.dispatch.<name>] section to enable one."
            )
            assert dp.note(app.screen, "items") == "Select a queue to see its items."

    dp.run(scenario)


def test_a_queue_list_that_cannot_load_says_why():
    async def scenario() -> None:
        link = support.FakeLink()
        async with dp.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("D")
            await support.until(lambda: dp.note(app.screen, "queues"))
            assert dp.note(app.screen, "queues") == "Could not load queues: /api/dispatch/queues"

    dp.run(scenario)


def test_the_first_queue_is_selected_and_its_items_list_newest_first():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.item_list(screen).option_count == 5)
            assert dp.highlighted(dp.queue_list(screen)) == "plans"
            assert dp.ids(dp.item_list(screen)) == ["p-gone", "p-pend", "p-run", "p-done", "p-fail"]
            assert at.prompts(dp.item_list(screen)) == [
                "cancelled  p-gone", "pending  p-pend", "running  p-run", "done  p-done  exit 0",
                "failed  p-fail  exit 2",
            ]
            assert dp.items_path("plans") in link.gets
            assert dp.items_path("reviews") not in link.gets

    dp.run(scenario)


def test_an_empty_queue_says_so_and_a_failing_items_read_says_why():
    async def scenario() -> None:
        link = await stocked()
        link.get_replies[dp.items_path("plans")] = {"items": []}
        del link.get_replies[dp.items_path("reviews")]
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.note(screen, "items") == "No items on this queue.")
            dp.queue_list(screen).highlighted = 1
            await support.until(lambda: dp.note(screen, "items").startswith("Could not load items"))
            assert dp.note(screen, "items") == f"Could not load items: {dp.items_path('reviews')}"
            assert dp.item_list(screen).option_count == 0

    dp.run(scenario)


def test_moving_to_another_queue_loads_its_items():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.item_list(screen).option_count == 5)
            dp.queue_list(screen).focus()
            await pilot.press("j")
            await support.until(lambda: dp.ids(dp.item_list(screen)) == ["r-run"])
            assert dp.items_path("reviews") in link.gets

    dp.run(scenario)


def test_a_reply_for_a_queue_the_operator_has_left_is_dropped():
    async def scenario() -> None:
        link = await stocked()
        link.holds[dp.items_path("plans")] = asyncio.Event()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.items_path("plans") in link.gets)
            dp.queue_list(screen).highlighted = 1
            await support.until(lambda: dp.ids(dp.item_list(screen)) == ["r-run"])
            link.holds[dp.items_path("plans")].set()
            await dp.settle()
            await pilot.pause()
            assert dp.ids(dp.item_list(screen)) == ["r-run"]
            assert screen.queue == "reviews"

    dp.run(scenario)


def test_the_detail_shows_the_loaded_row_with_its_fields():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.item_list(screen).option_count == 5)
            dp.item_list(screen).highlighted = 3
            await support.until(lambda: "p-done" in dp.detail(screen))
            gets = len(link.gets)
            assert dp.detail(screen).splitlines() == [
                "plans  p-done  done",
                "command   workhorse-plans-runner",
                "pid       4242",
                "exit code 0",
                "started   2023-11-14 22:13:35",
                "run id    run-a",
                "params",
                "  {",
                '    "plan_path": "docs/a.md",',
                '    "cli": "codex"',
                "  }",
            ]
            dp.item_list(screen).highlighted = 1
            await support.until(lambda: "p-pend" in dp.detail(screen))
            assert "pid       —" in dp.detail(screen)
            assert "exit code —" in dp.detail(screen)
            assert len(link.gets) == gets

    dp.run(scenario)


def test_the_detail_says_so_when_the_item_left_the_queue():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.item_list(screen).option_count == 5)
            dp.item_list(screen).highlighted = 2
            await support.until(lambda: "p-run" in dp.detail(screen))
            link.get_replies[dp.items_path("plans")] = {"items": []}
            screen._tick()
            await support.until(lambda: dp.note(screen, "items") == "No items on this queue.")
            assert dp.detail(screen) == "That item is no longer on this queue."

    dp.run(scenario)


def test_the_poll_interval_is_five_seconds():
    assert screen_module.POLL_S == 5.0


def test_the_screen_polls_while_open_and_stops_when_it_closes(monkeypatch):
    async def scenario() -> None:
        monkeypatch.setattr(screen_module, "POLL_S", 0.1)
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: link.gets.count(dp.QUEUES) >= 3)
            assert link.gets.count(dp.items_path("plans")) >= 3
            assert link.gets.count(dp.items_path("reviews")) == 0
            await pilot.press("escape")
            await support.until(lambda: app.screen is app.main)
            await dp.settle()
            seen = list(link.gets)
            await asyncio.sleep(0.4)
            assert link.gets == seen
            assert screen.is_attached is False

    dp.run(scenario)


def test_a_poll_keeps_the_highlighted_queue_and_item_and_shows_no_loading_text():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            dp.queue_list(screen).highlighted = 1
            await support.until(lambda: dp.ids(dp.item_list(screen)) == ["r-run"])
            dp.put("r-new", "reviews", "pending", at_=dp.T0 + 99)
            dp.put("r-old", "reviews", "done", at_=dp.T0 + 1, exit_code=0)
            await dp.serve(link)
            await support.until(lambda: "r-run" in dp.detail(screen))
            before = len(link.gets)
            screen._tick()
            await support.until(lambda: dp.ids(dp.item_list(screen)) == ["r-new", "r-run", "r-old"])
            await dp.settle()
            assert dp.highlighted(dp.queue_list(screen)) == "reviews"
            assert dp.highlighted(dp.item_list(screen)) == "r-run"
            assert "r-run" in dp.detail(screen)
            assert dp.note(screen, "queues") == ""
            assert dp.note(screen, "items") == ""
            assert len(link.gets) > before

    dp.run(scenario)


def test_the_screen_keys_switch_between_attendant_dispatch_and_settings():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            await dp.open_dispatch(app, pilot, link)
            await pilot.press("A")
            await support.until(lambda: isinstance(app.screen, AttendScreen))
            await pilot.press("D")
            await support.until(lambda: isinstance(app.screen, screen_module.DispatchScreen))
            await pilot.press("S")
            await support.until(lambda: isinstance(app.screen, SettingsScreen))
            await pilot.press("D")
            await support.until(lambda: isinstance(app.screen, screen_module.DispatchScreen))
            assert len(app.screen_stack) == 2
            await pilot.press("escape")
            await support.until(lambda: app.screen is app.main)

    dp.run(scenario)


def test_a_load_error_in_a_later_poll_keeps_the_rows_and_names_the_reason():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            link.get_replies.pop(dp.QUEUES)
            screen._tick()
            await support.until(lambda: dp.note(screen, "queues").startswith("Could not load queues"))
            assert dp.queue_list(screen).option_count == 2

    dp.run(scenario)


def test_a_long_queue_fills_in_chunks_and_a_poll_neither_truncates_nor_moves_the_highlight(monkeypatch):
    async def scenario() -> None:
        monkeypatch.setattr(screen_module, "CHUNK", 3)
        link = support.FakeLink()
        for number in range(8):
            dp.put(f"q-{number}", "plans", "done", at_=dp.T0 + number, exit_code=0)
        await dp.serve(link)
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            await support.until(lambda: dp.item_list(screen).option_count == 8)
            assert dp.ids(dp.item_list(screen)) == [f"q-{number}" for number in range(7, -1, -1)]
            assert dp.highlighted(dp.item_list(screen)) == "q-7"
            dp.item_list(screen).highlighted = 6
            await support.until(lambda: "q-1" in dp.detail(screen))
            screen._tick()
            await dp.settle()
            assert dp.item_list(screen).option_count == 8
            assert dp.highlighted(dp.item_list(screen)) == "q-1"

    dp.run(scenario)
