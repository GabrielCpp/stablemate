from __future__ import annotations

import time

import _attend_support as at
import _tui_support as support
from textual.widgets import OptionList

from groom.tui.route import route
from groom.tui.screens.attend import AttendScreen

async def stock(link: support.FakeLink) -> None:
    at.begin("j-done", "run-running", workflow="author", session="s-done", reason="stuck on a gate", started_at=at.T0)
    at.end("j-done", 0, "blocked", at.T0 + 90)
    at.begin("j-dead", "run-done", workflow="", session="s-b1", reason="", kind="dead", started_at=at.T0 + 100, node="")
    at.attend_ledger.attend_append_session("j-dead", "s-b2", 11)
    at.end("j-dead", 1, "", at.T0 + 4000)
    at.begin("j-live", "run-blocked", session="s-live", started_at=time.time() - 30)
    at.write_transcript("s-done", at.CONVERSATION, at.SIDECHAIN)
    at.write_transcript("s-live", [at.turn("assistant", [{"type": "text", "text": "working"}])])
    await at.serve_sessions(link)
    for session in ("s-done", "s-b2", "s-live"):
        await at.serve_session(link, session)


async def open_attend(app, pilot, link, rows: int = 3) -> AttendScreen:
    link.push(support.state_frame())
    await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
    await pilot.press("A")
    await support.until(lambda: isinstance(app.screen, AttendScreen))
    await support.until(lambda: app.screen.query_one("#attend-list", OptionList).option_count == rows)
    return app.screen


def listing(screen) -> OptionList:
    return screen.query_one("#attend-list", OptionList)


def ids(screen) -> list[str]:
    view = listing(screen)
    return [str(view.get_option_at_index(i).id) for i in range(view.option_count)]


def highlighted(screen) -> str:
    view = listing(screen)
    assert view.highlighted is not None
    return str(view.get_option_at_index(view.highlighted).id)


def note(screen) -> str:
    return at.static(screen, "#attend-note")


def empty(screen) -> str:
    return at.static(screen, "#attend-empty")


async def read(pilot, screen, job_id: str, link, session: str) -> None:
    view = listing(screen)
    view.highlighted = ids(screen).index(job_id)
    await pilot.press("enter")
    await support.until(lambda: route(at.SESSIONS, session) in link.gets)
    await pilot.pause()
