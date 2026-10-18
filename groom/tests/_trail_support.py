from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import _tui_support as support
from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Collapsible, OptionList, Static
from textual.widgets._collapsible import CollapsibleTitle

from groom.tui.app import GroomTui
from groom.tui.widgets.lines import PlainLine, TurnGroup
from groom.tui.widgets.trail import TrailTab

HOSTILE = "evil\x1b]52;c;ZXZpbA==\x07\x1b[2Jtext"
DONE = "001-implement"
LIVE = "002-review"


@asynccontextmanager
async def booted(link: support.FakeLink) -> AsyncIterator[tuple[GroomTui, Pilot]]:
    app = GroomTui(link)
    async with app.run_test(size=(140, 50)) as pilot:
        yield app, pilot


def run(scenario: Callable[[], Coroutine[None, None, None]]) -> None:
    asyncio.run(scenario())


def rows() -> list[dict]:
    return [
        support.log_row(100.0, "compiled the plan"),
        support.log_row(110.0, "tests failed", severity="ERROR"),
        support.span_row(120.0, "plan"),
        support.metric_row(130.0),
        support.transcript_row(140.0, support.message_update("user_message_chunk", "do it"), DONE),
        support.transcript_row(141.0, support.message_update("agent_message_chunk", "I **did** it"), DONE),
        support.transcript_row(142.0, support.tool_update("ls", "a.txt"), DONE),
        support.span_row(150.0, "agent_turn", DONE),
        support.transcript_row(160.0, support.message_update("agent_message_chunk", "reviewing"), LIVE, "review"),
    ]


async def open_run(app: GroomTui, pilot: Pilot, link: support.FakeLink, container: str, rows: list[dict]) -> None:
    link.push(support.state_frame())
    await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
    await app.open_run(container)
    link.push(support.history_frame(container, rows))
    await support.until(lambda: app.store.detail is not None)
    await pilot.pause()


async def push_detail(app: GroomTui, pilot: Pilot, link: support.FakeLink, container: str, rows: list[dict]) -> None:
    before = app.store.detail
    link.push(support.history_frame(container, rows))
    await support.until(lambda: app.store.detail is not before)
    await pilot.pause()


def trail(app: GroomTui) -> TrailTab:
    return app.query_one(TrailTab)


def children(app: GroomTui) -> list[Any]:
    return list(trail(app).query_one("#trail-lines").children)


def plain(app: GroomTui, selector: str) -> str:
    content = app.query_one(selector, Static).content
    return content.plain if isinstance(content, Text) else str(content)


def bodies(app: GroomTui) -> list[str]:
    return [line.data["body"] for line in trail(app).query(PlainLine)]


def turns(app: GroomTui) -> dict[str, TurnGroup]:
    return {group.slug: group for group in trail(app).query(TurnGroup)}


def label(group: Collapsible) -> str:
    return Content.from_text(group.query_one(CollapsibleTitle).label).plain


def visible_text(app: GroomTui) -> str:
    parts: list[str] = []

    def take(renderable: Any) -> None:
        if isinstance(renderable, Group):
            for inner in renderable.renderables:
                take(inner)
        elif isinstance(renderable, Markdown):
            parts.append(renderable.markup)
        elif isinstance(renderable, Text):
            parts.append(renderable.plain)
        else:
            parts.append(str(renderable))

    for widget in app.query(Static):
        if not isinstance(widget, CollapsibleTitle):
            take(widget.content)
    for title in app.query(CollapsibleTitle):
        parts.append(Content.from_text(title.label).plain)
    return "\n".join(parts)
