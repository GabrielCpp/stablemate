from __future__ import annotations

import time

import _attend_support as at
import _dispatch_support as dp
import _tui_support as support
import pytest

from groom import state
from groom.tui.link import LinkError
from groom.tui.screens.confirm import Confirm


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


async def open_on(app, pilot, link, item_id: str):
    screen = await dp.open_dispatch(app, pilot, link)
    await support.until(lambda: dp.item_list(screen).option_count == 5)
    dp.item_list(screen).highlighted = dp.ids(dp.item_list(screen)).index(item_id)
    await support.until(lambda: item_id in dp.detail(screen))
    return screen


def test_c_on_a_pending_item_asks_and_yes_deletes_it_then_refetches():
    async def scenario() -> None:
        link = await stocked()
        link.delete_replies[dp.item_path("plans", "p-pend")] = {"ok": True}
        async with dp.booted(link) as (app, pilot):
            screen = await open_on(app, pilot, link, "p-pend")
            before = link.gets.count(dp.QUEUES)
            await pilot.press("c")
            await support.until(lambda: isinstance(app.screen, Confirm))
            assert "Cancel p-pend? It never starts." in at.screen_text(app.screen)
            assert link.deletes == []
            await pilot.press("y")
            await support.until(lambda: link.deletes)
            assert link.deletes == [dp.item_path("plans", "p-pend")]
            assert link.post_log == []
            await support.until(lambda: link.gets.count(dp.QUEUES) > before)
            assert app.screen is screen
            assert dp.toasts(app) == []

    dp.run(scenario)


@pytest.mark.parametrize("key", ["n", "escape"])
def test_no_or_escape_on_the_cancel_confirm_deletes_nothing(key):
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await open_on(app, pilot, link, "p-pend")
            await pilot.press("c")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press(key)
            await support.until(lambda: app.screen is screen)
            await dp.settle()
            assert link.deletes == []

    dp.run(scenario)


def test_a_cancel_that_finds_the_item_started_says_so_and_refetches():
    async def scenario() -> None:
        link = await stocked()
        link.delete_replies[dp.item_path("plans", "p-pend")] = {"ok": False}
        async with dp.booted(link) as (app, pilot):
            await open_on(app, pilot, link, "p-pend")
            before = link.gets.count(dp.items_path("plans"))
            await pilot.press("c")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press("y")
            await support.until(lambda: dp.toasts(app) == ["That item was already running or done."])
            await support.until(lambda: link.gets.count(dp.items_path("plans")) > before)

    dp.run(scenario)


def test_x_on_a_running_item_asks_and_yes_posts_the_stop_then_refetches():
    async def scenario() -> None:
        link = await stocked()
        link.post_replies[dp.item_path("plans", "p-run") + "/stop"] = {"ok": True}
        async with dp.booted(link) as (app, pilot):
            screen = await open_on(app, pilot, link, "p-run")
            before = link.gets.count(dp.QUEUES)
            await pilot.press("x")
            await support.until(lambda: isinstance(app.screen, Confirm))
            assert "Stop p-run? Its process is killed." in at.screen_text(app.screen)
            assert link.post_log == []
            await pilot.press("y")
            await support.until(lambda: link.post_log)
            assert link.post_log == [(dp.item_path("plans", "p-run") + "/stop", None)]
            assert link.deletes == []
            await support.until(lambda: link.gets.count(dp.QUEUES) > before)
            assert app.screen is screen
            assert dp.toasts(app) == []

    dp.run(scenario)


@pytest.mark.parametrize("key", ["n", "escape"])
def test_no_or_escape_on_the_stop_confirm_posts_nothing(key):
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await open_on(app, pilot, link, "p-run")
            await pilot.press("x")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press(key)
            await support.until(lambda: app.screen is screen)
            await dp.settle()
            assert link.post_log == []

    dp.run(scenario)


def test_a_stop_that_finds_the_item_gone_says_so_and_refetches():
    async def scenario() -> None:
        link = await stocked()
        link.post_replies[dp.item_path("plans", "p-run") + "/stop"] = {"ok": False}
        async with dp.booted(link) as (app, pilot):
            await open_on(app, pilot, link, "p-run")
            before = link.gets.count(dp.items_path("plans"))
            await pilot.press("x")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press("y")
            await support.until(lambda: dp.toasts(app) == ["That item was already gone."])
            await support.until(lambda: link.gets.count(dp.items_path("plans")) > before)

    dp.run(scenario)


def test_a_stop_or_cancel_groom_does_not_answer_toasts_the_reason():
    async def scenario() -> None:
        link = await stocked()
        link.post_replies[dp.item_path("plans", "p-run") + "/stop"] = LinkError("HTTP 500: store is locked")
        link.delete_replies[dp.item_path("plans", "p-pend")] = LinkError("HTTP 500: store is locked")
        async with dp.booted(link) as (app, pilot):
            await open_on(app, pilot, link, "p-run")
            await pilot.press("x")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press("y")
            await support.until(lambda: dp.toasts(app) == ["groom did not answer the stop: HTTP 500: store is locked"])
            screen = app.screen
            dp.item_list(screen).highlighted = dp.ids(dp.item_list(screen)).index("p-pend")
            await support.until(lambda: "p-pend" in dp.detail(screen))
            await pilot.press("c")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press("y")
            await support.until(lambda: len(dp.toasts(app)) == 2)
            assert dp.toasts(app)[1] == "groom did not answer the cancel: HTTP 500: store is locked"

    dp.run(scenario)


@pytest.mark.parametrize(
    ("item_id", "key"),
    [("p-run", "c"), ("p-pend", "x"), ("p-done", "c"), ("p-done", "x"), ("p-fail", "x"), ("p-gone", "c")],
)
def test_keys_that_do_not_fit_the_highlighted_item_do_nothing(item_id, key):
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await open_on(app, pilot, link, item_id)
            await pilot.press(key)
            await dp.settle()
            assert app.screen is screen
            assert link.deletes == [] and link.post_log == []

    dp.run(scenario)


def test_the_footer_offers_cancel_only_on_pending_and_stop_only_on_running():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await open_on(app, pilot, link, "p-pend")
            assert screen.check_action("cancel_item", ()) is True
            assert screen.check_action("stop_item", ()) is False
            assert screen.check_action("enqueue", ()) is True
            dp.item_list(screen).highlighted = dp.ids(dp.item_list(screen)).index("p-run")
            await support.until(lambda: "p-run" in dp.detail(screen))
            assert screen.check_action("cancel_item", ()) is False
            assert screen.check_action("stop_item", ()) is True
            dp.item_list(screen).highlighted = dp.ids(dp.item_list(screen)).index("p-done")
            await support.until(lambda: "p-done" in dp.detail(screen))
            assert screen.check_action("cancel_item", ()) is False
            assert screen.check_action("stop_item", ()) is False

    dp.run(scenario)


def test_hostile_queue_command_item_and_params_reach_the_widgets_without_control_bytes(tmp_path):
    async def scenario() -> None:
        hostile = dp.HOSTILE
        dp.write_config(tmp_path, {hostile: dict(command=hostile, concurrency=1)})
        dp.put(hostile, hostile, "running", params={hostile: hostile, "n": [hostile]}, run_id=hostile)
        link = support.FakeLink()
        await dp.serve(link)
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link, queues=1)
            await support.until(lambda: dp.item_list(screen).option_count == 1)
            await support.until(lambda: "eviltext" in dp.detail(screen))
            shown = dp.whole(screen)
            assert "eviltext" in shown
            assert not set(dp.CONTROLS) & set(shown)
            await pilot.press("x")
            await support.until(lambda: isinstance(app.screen, Confirm))
            assert not set(dp.CONTROLS) & set(at.screen_text(app.screen))
            assert "Stop eviltext? Its process is killed." in at.screen_text(app.screen)
            link.post_replies[dp.item_path(hostile, hostile) + "/stop"] = LinkError(f"HTTP 500: {hostile}")
            await pilot.press("y")
            await support.until(lambda: dp.toasts(app))
            assert not set(dp.CONTROLS) & set(dp.toasts(app)[0])
            assert dp.toasts(app) == ["groom did not answer the stop: HTTP 500: eviltext"]

    dp.run(scenario)
