from __future__ import annotations

import time

import _attend_support as at
import _dispatch_support as dp
import _tui_support as support
import pytest
from textual.widgets import Input, OptionList, Select, Static

from groom import app as groom_app
from groom import dispatch_ledger, state
from groom.tui.link import LinkError
from groom.tui.screens.confirm import Confirm
from groom.tui.screens.enqueue import EnqueueForm


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


async def open_form(app, pilot, link) -> EnqueueForm:
    screen = await dp.open_dispatch(app, pilot, link)
    await support.until(lambda: dp.item_list(screen).option_count == 5)
    await pilot.press("n")
    await support.until(lambda: isinstance(app.screen, EnqueueForm))
    return app.screen


def accepted(item_id: str = "p-new") -> dict:
    dp.put(item_id, "plans", "pending", at_=dp.T0 + 99)
    return {"ok": True, "item": dispatch_ledger.dispatch_get(item_id)}


async def refused_by_groom() -> str:
    reply = await groom_app.dispatch_enqueue.fn("no-such", {"params": {}})
    return reply.content["error"]


def labels(form: EnqueueForm) -> list[str]:
    return [at.flatten(widget.content) for widget in form.query(".enqueue-label").results(Static)]


def test_the_form_has_one_field_per_param_with_its_label_default_and_star():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            assert labels(form) == ["Plan path *", "Agent CLI", "note", "mode"]
            plan, note = form.query_one("#enqueue-0", Input), form.query_one("#enqueue-2", Input)
            assert (plan.value, note.value) == ("", "nightly")
            cli, mode = form.query_one("#enqueue-1", Select), form.query_one("#enqueue-3", Select)
            assert cli.value == "claude"
            assert cli.is_blank() is False
            assert mode.is_blank()
            assert [value for _, value in cli._options] == ["claude", "codex"]
            assert [value for _, value in mode._options if isinstance(value, str)] == ["fast", "slow"]
            assert app.focused is plan
            assert "Enqueue on plans" in at.screen_text(form)

    dp.run(scenario)


def test_ctrl_s_with_a_required_field_empty_names_the_field_and_posts_nothing():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            await pilot.press("ctrl+s")
            await support.until(lambda: dp.toasts(app))
            assert dp.toasts(app) == ["Plan path is required."]
            assert link.post_log == []
            assert app.screen is form
            assert app.focused is form.query_one("#enqueue-0")
            form.query_one("#enqueue-0", Input).value = "   "
            await pilot.press("ctrl+s")
            await dp.settle()
            assert link.post_log == []

    dp.run(scenario)


def test_ctrl_s_posts_every_field_as_a_string_then_closes_toasts_and_refetches():
    async def scenario() -> None:
        link = await stocked()

        async def enqueue(body):
            reply = accepted()
            await dp.serve(link)
            return reply

        link.post_handlers[dp.items_path("plans")] = enqueue
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            before = link.gets.count(dp.QUEUES)
            for key in "docs/x.md":
                await pilot.press("slash" if key == "/" else key)
            form.query_one("#enqueue-1", Select).value = "codex"
            await pilot.press("ctrl+s")
            await support.until(lambda: link.post_log)
            assert link.post_log == [(dp.items_path("plans"), {"params": {
                "plan_path": "docs/x.md", "cli": "codex", "note": "nightly", "mode": "",
            }})]
            await support.until(lambda: app.screen is not form)
            assert dp.toasts(app) == ["Enqueued p-new on plans."]
            await support.until(lambda: link.gets.count(dp.QUEUES) > before)
            await support.until(lambda: "p-new" in dp.ids(dp.item_list(app.screen)))

    dp.run(scenario)


def test_the_enqueue_button_and_enter_in_a_field_also_submit():
    async def scenario() -> None:
        link = await stocked()
        link.post_replies[dp.items_path("plans")] = accepted()
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            form.query_one("#enqueue-0", Input).value = "docs/a.md"
            await pilot.click("#enqueue-send")
            await support.until(lambda: len(link.post_log) == 1)
            await support.until(lambda: app.screen is not form)
            form = await open_form(app, pilot, link)
            form.query_one("#enqueue-0", Input).value = "docs/b.md"
            await pilot.press("enter")
            await support.until(lambda: len(link.post_log) == 2)
            assert dp.posted(link, 1)["params"]["plan_path"] == "docs/b.md"

    dp.run(scenario)


def test_escape_and_the_cancel_button_close_the_form_without_a_post():
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            await pilot.press("escape")
            await support.until(lambda: app.screen is not form)
            form = await open_form(app, pilot, link)
            await pilot.click("#enqueue-cancel")
            await support.until(lambda: app.screen is not form)
            assert link.post_log == []

    dp.run(scenario)


def test_a_404_keeps_the_form_open_and_toasts_the_error_groom_sent():
    async def scenario() -> None:
        reason = await refused_by_groom()
        link = await stocked()
        link.post_replies[dp.items_path("plans")] = LinkError(f"POST /x: HTTP 404: {reason}")
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            before = link.gets.count(dp.QUEUES)
            form.query_one("#enqueue-0", Input).value = "docs/x.md"
            await pilot.press("ctrl+s")
            await support.until(lambda: dp.toasts(app))
            assert dp.toasts(app) == ["groom did not accept the item: POST /x: HTTP 404: no such queue: no-such"]
            await support.until(lambda: link.gets.count(dp.QUEUES) > before)
            assert app.screen is form
            assert form.query_one("#enqueue-0", Input).value == "docs/x.md"
            await pilot.press("ctrl+s")
            await support.until(lambda: len(link.post_log) == 2)

    dp.run(scenario)


def test_an_ok_false_reply_keeps_the_form_open_with_groom_s_reason():
    async def scenario() -> None:
        reason = await refused_by_groom()
        link = await stocked()
        link.post_replies[dp.items_path("plans")] = {"ok": False, "error": reason}
        async with dp.booted(link) as (app, pilot):
            form = await open_form(app, pilot, link)
            form.query_one("#enqueue-0", Input).value = "docs/x.md"
            await pilot.press("ctrl+s")
            await support.until(lambda: dp.toasts(app))
            assert dp.toasts(app) == ["groom did not accept the item: no such queue: no-such"]
            assert app.screen is form

    dp.run(scenario)


def test_a_queue_without_params_asks_and_yes_posts_an_empty_params_object():
    async def scenario() -> None:
        link = await stocked()
        link.post_replies[dp.items_path("reviews")] = accepted("r-new")
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            dp.queue_list(screen).highlighted = 1
            await support.until(lambda: dp.ids(dp.item_list(screen)) == ["r-run"])
            await pilot.press("n")
            await support.until(lambda: isinstance(app.screen, Confirm))
            assert "Enqueue on reviews?" in at.screen_text(app.screen)
            assert link.post_log == []
            await pilot.press("y")
            await support.until(lambda: link.post_log)
            assert link.post_log == [(dp.items_path("reviews"), {"params": {}})]
            await support.until(lambda: dp.toasts(app) == ["Enqueued r-new on reviews."])

    dp.run(scenario)


@pytest.mark.parametrize("key", ["n", "escape"])
def test_no_or_escape_on_the_enqueue_confirm_posts_nothing(key):
    async def scenario() -> None:
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            screen = await dp.open_dispatch(app, pilot, link)
            dp.queue_list(screen).highlighted = 1
            await support.until(lambda: dp.ids(dp.item_list(screen)) == ["r-run"])
            await pilot.press("n")
            await support.until(lambda: isinstance(app.screen, Confirm))
            await pilot.press(key)
            await support.until(lambda: app.screen is screen)
            await dp.settle()
            assert link.post_log == []

    dp.run(scenario)


def test_n_with_no_queue_selected_does_nothing(tmp_path):
    async def scenario() -> None:
        dp.write_config(tmp_path, {})
        link = await stocked()
        async with dp.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("D")
            await support.until(lambda: dp.note(app.screen, "queues"))
            screen = app.screen
            await pilot.press("n")
            await dp.settle()
            assert app.screen is screen

    dp.run(scenario)


def test_a_hostile_label_default_and_option_reach_the_form_without_control_bytes(tmp_path):
    async def scenario() -> None:
        hostile = dp.HOSTILE
        dp.write_config(tmp_path, {"plans": dict(command="workhorse-plan-runner", params=[
            dict(name="plan", label=hostile, required=True, default=hostile),
            dict(name="cli", label=hostile, type="select", options=[hostile, "codex"], default=hostile),
        ])})
        link = support.FakeLink()
        await dp.serve(link)
        link.post_replies[dp.items_path("plans")] = accepted()
        async with dp.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("D")
            await support.until(lambda: dp.queue_list(app.screen).option_count == 1)
            await pilot.press("n")
            await support.until(lambda: isinstance(app.screen, EnqueueForm))
            form = app.screen
            assert isinstance(form, EnqueueForm)
            assert not set(dp.CONTROLS) & set("".join(labels(form)))
            assert not set(dp.CONTROLS) & set(form.query_one("#enqueue-0", Input).value)
            assert form.query_one("#enqueue-1", Select).value == "eviltext"
            await pilot.press("ctrl+s")
            await support.until(lambda: link.post_log)
            posted = dp.posted(link, 0)["params"]
            assert posted == {"plan": "eviltext", "cli": "eviltext"}

    dp.run(scenario)
