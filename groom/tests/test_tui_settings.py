from __future__ import annotations

import _attend_support as at
import _tui_support as support
import _trail_support as tr
import pytest
from textual.widgets import Static, Switch

from groom import app as groom_app
from groom import attend, state
from groom.tui.link import LinkError
from groom.tui.screens.settings import SettingsScreen


@pytest.fixture(autouse=True)
def _groom(tmp_path, monkeypatch):
    at.isolate(tmp_path, monkeypatch, "headless")
    support.seed()
    yield
    state.WORKFLOWS.clear()
    at.release()


def text(screen, name: str) -> str:
    return at.flatten(screen.query_one(f"#settings-{name}", Static).content)


async def open_settings(app, pilot, link) -> SettingsScreen:
    link.push(support.state_frame())
    await support.until(lambda: app.main.query_one("#runs").option_count == 3)
    await pilot.press("S")
    await support.until(lambda: isinstance(app.screen, SettingsScreen))
    return app.screen


def test_the_panel_loads_with_the_switch_the_mode_and_where_the_value_came_from():
    async def scenario() -> None:
        link = support.FakeLink()
        await at.serve_settings(link)
        link.holds[at.SETTINGS] = support.asyncio.Event()
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            await support.until(lambda: at.SETTINGS in link.gets)
            await pilot.pause()
            assert text(screen, "note") == "Loading settings…"
            assert not screen.query_one("#settings-panel").display
            link.holds[at.SETTINGS].set()
            await support.until(lambda: screen.query_one("#settings-panel").display)
            assert text(screen, "note") == ""
            assert text(screen, "label") == "Attend parked and dead runs"
            assert screen.query_one(Switch).value is True
            assert text(screen, "mode") == "headless"
            assert "headless mode spawns claude" in text(screen, "why")
            assert "session mode only publishes" in text(screen, "why")
            assert text(screen, "source") == "value from environment. The config is not carrying this key."
            assert link.gets == [at.SETTINGS]

    tr.run(scenario)


def test_an_off_mode_from_the_default_shows_the_switch_off():
    async def scenario() -> None:
        link = support.FakeLink()
        at.release()
        import os

        os.environ.pop("GROOM_ATTEND")
        attend.forget_settings()
        await at.serve_settings(link)
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            await support.until(lambda: screen.query_one(Switch).has_focus)
            assert screen.query_one(Switch).value is False
            assert text(screen, "mode") == "off"
            assert text(screen, "source") == "value from default"

    tr.run(scenario)


def test_toggling_posts_the_body_shows_saving_and_then_the_returned_settings():
    async def scenario() -> None:
        link = support.FakeLink()
        await at.serve_settings(link)
        link.holds[at.SETTINGS] = support.asyncio.Event()
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            link.holds[at.SETTINGS].set()
            await support.until(lambda: screen.query_one(Switch).has_focus)
            link.holds[at.SETTINGS] = support.asyncio.Event()
            await pilot.press("space")
            await support.until(lambda: link.post_log)
            assert link.post_log == [(at.SETTINGS, {"enabled": False})]
            await support.until(lambda: text(screen, "mode") == "headless · saving…")
            assert screen.query_one(Switch).disabled
            assert screen.query_one(Switch).value is False
            link.holds[at.SETTINGS].set()
            await support.until(lambda: text(screen, "mode") == "off")
            assert not screen.query_one(Switch).disabled
            assert screen.query_one(Switch).value is False
            assert text(screen, "source") == "value from config"
            assert len(link.post_log) == 1
            assert not app._notifications

    tr.run(scenario)


def test_a_refused_save_toasts_and_puts_the_switch_back():
    async def scenario() -> None:
        link = support.FakeLink()
        await at.serve_settings(link)
        link.post_handlers.pop(at.SETTINGS)
        link.post_replies[at.SETTINGS] = LinkError("POST /api/settings/attend: HTTP 500: disk full")
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            await support.until(lambda: screen.query_one(Switch).has_focus)
            await pilot.press("space")
            await support.until(lambda: app._notifications)
            assert [n.message for n in app._notifications] == [
                "groom did not accept the setting: POST /api/settings/attend: HTTP 500: disk full"
            ]
            await support.until(lambda: not screen.query_one(Switch).disabled)
            assert screen.query_one(Switch).value is True
            assert text(screen, "mode") == "headless"

    tr.run(scenario)


def test_a_failed_load_says_why_and_shows_no_panel():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            await support.until(lambda: text(screen, "note").startswith("Could not load settings: "))
            assert not screen.query_one("#settings-panel").display

    tr.run(scenario)


def test_the_real_save_writes_the_config_and_reads_back_off_then_on():
    async def scenario() -> None:
        link = support.FakeLink()
        await at.serve_settings(link)
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            await support.until(lambda: screen.query_one(Switch).has_focus)
            await pilot.press("space")
            await support.until(lambda: text(screen, "mode") == "off")
            await pilot.press("space")
            await support.until(lambda: text(screen, "mode") == "headless")
            assert [body for _path, body in link.post_log] == [{"enabled": False}, {"enabled": True}]
            assert (await groom_app.attend_settings_get.fn())["mode"] == "headless"

    tr.run(scenario)


def test_hostile_settings_strings_reach_the_widgets_without_control_bytes():
    async def scenario() -> None:
        link = support.FakeLink()
        link.get_replies[at.SETTINGS] = {"mode": at.HOSTILE, "cli": at.HOSTILE, "sources": {"mode": at.HOSTILE}}
        async with tr.booted(link) as (app, pilot):
            screen = await open_settings(app, pilot, link)
            await support.until(lambda: screen.query_one(Switch).has_focus)
            shown = at.screen_text(screen)
            assert "eviltext" in shown
            assert not any(ch in shown for ch in at.CONTROLS)

    tr.run(scenario)
