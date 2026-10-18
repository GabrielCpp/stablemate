from __future__ import annotations

import _tui_support as support
import _trail_support as tr
import pytest
from textual.widgets import Collapsible, Static
from textual.widgets._collapsible import CollapsibleTitle

from groom import state
from groom.tui.widgets import trail as trail_module
from groom.tui.widgets.lines import PlainLine


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


def test_a_running_turn_is_open_and_a_done_turn_is_closed():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, tr.rows())
            turns = tr.turns(app)
            assert not turns[tr.LIVE].collapsed
            assert turns[tr.DONE].collapsed
            title = tr.label(turns[tr.DONE])
            assert title.split()[-4:] == ["implement", tr.DONE, "done", "2.0s"]
            assert "running" in tr.label(turns[tr.LIVE])

    tr.run(scenario)


def test_a_toggled_turn_keeps_its_choice_across_a_new_detail_frame():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            rows = tr.rows()
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            turns = tr.turns(app)
            for slug in (tr.LIVE, tr.DONE):
                title = turns[slug].query_one(CollapsibleTitle)
                title.focus()
                await pilot.press("enter")
                await pilot.pause()
            assert turns[tr.LIVE].collapsed
            assert not turns[tr.DONE].collapsed
            more = [*rows, support.log_row(170.0, "another line")]
            await tr.push_detail(app, pilot, link, support.GLOBEX, more)
            assert tr.turns(app) == turns
            assert turns[tr.LIVE].collapsed
            assert not turns[tr.DONE].collapsed
            said = support.message_update("agent_message_chunk", "and more")
            grown = [
                *more,
                support.transcript_row(180.0, said, tr.LIVE, "review"),
                support.transcript_row(181.0, said, tr.DONE),
                support.span_row(182.0, "agent_turn", tr.LIVE),
            ]
            await tr.push_detail(app, pilot, link, support.GLOBEX, grown)
            assert tr.turns(app) == turns
            assert len(turns[tr.LIVE].query(".entry-message")) == 2
            assert turns[tr.LIVE].collapsed
            assert not turns[tr.DONE].collapsed
            assert "done" in tr.label(turns[tr.LIVE])

    tr.run(scenario)


def test_an_untouched_running_turn_closes_when_it_finishes():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            rows = tr.rows()
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            live = tr.turns(app)[tr.LIVE]
            assert not live.collapsed
            await tr.push_detail(app, pilot, link, support.GLOBEX, [*rows, support.span_row(180.0, "agent_turn", tr.LIVE)])
            assert tr.turns(app)[tr.LIVE] is live
            assert live.collapsed

    tr.run(scenario)


def test_hostile_trail_text_reaches_the_screen_without_control_bytes():
    async def scenario() -> None:
        rows = [
            support.log_row(100.0, f"body {tr.HOSTILE}"),
            support.transcript_row(
                140.0, support.message_update("agent_message_chunk", f"said {tr.HOSTILE}"), tr.DONE
            ),
            support.transcript_row(141.0, support.message_update("user_message_chunk", f"asked {tr.HOSTILE}"), tr.DONE),
            support.transcript_row(142.0, support.tool_update("ls [b]x[/b]", f"result {tr.HOSTILE}"), tr.DONE),
            support.span_row(150.0, "agent_turn", tr.DONE),
        ]
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            seen = tr.visible_text(app)
            for needle in ("body eviltext", "said eviltext", "asked eviltext", "result eviltext"):
                assert needle in seen
            assert "ls [b]x[/b]" in seen
            for forbidden in ("\x1b", "\x07", "ZXZpbA", "[2J"):
                assert forbidden not in seen
            assert "\x1b" not in app.export_screenshot()

    tr.run(scenario)


def test_an_identical_detail_frame_leaves_every_trail_widget_the_same_object():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            rows = tr.rows()
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            before = tr.children(app)
            entries = [list(group.query(Static)) for group in tr.turns(app).values()]
            assert len(before) == 6
            await tr.push_detail(app, pilot, link, support.GLOBEX, rows)
            after = tr.children(app)
            assert len(after) == len(before)
            assert all(a is b for a, b in zip(before, after, strict=True))
            assert entries == [list(group.query(Static)) for group in tr.turns(app).values()]

    tr.run(scenario)


def test_one_more_line_mounts_exactly_one_new_widget():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            rows = tr.rows()
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            before = tr.children(app)
            await tr.push_detail(app, pilot, link, support.GLOBEX, [*rows, support.log_row(170.0, "brand new")])
            after = tr.children(app)
            assert len(after) == len(before) + 1
            assert after[0].data["body"] == "brand new"
            assert after[1:] == before

    tr.run(scenario)


def test_a_gone_line_is_removed_and_the_rest_stay():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            rows = tr.rows()
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            before = tr.children(app)
            await tr.push_detail(app, pilot, link, support.GLOBEX, [row for row in rows if row["ts"] != 100.0])
            after = tr.children(app)
            assert len(after) == len(before) - 1
            assert after == before[:-1]

    tr.run(scenario)


def test_a_turn_gains_an_entry_in_place_and_moves_above_a_newer_line():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            first = support.transcript_row(140.0, support.message_update("agent_message_chunk", "one"), tr.LIVE)
            rows = [support.log_row(170.0, "later log"), first]
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            turn = tr.turns(app)[tr.LIVE]
            log = tr.children(app)[0]
            assert isinstance(log, PlainLine)
            assert tr.children(app) == [log, turn]
            entries = list(turn.query_one(Collapsible.Contents).children)
            second = support.transcript_row(200.0, support.message_update("agent_message_chunk", "two"), tr.LIVE)
            await tr.push_detail(app, pilot, link, support.GLOBEX, [*rows, second])
            assert tr.children(app) == [turn, log]
            now = list(turn.query_one(Collapsible.Contents).children)
            assert len(now) == 2
            assert now[0] is entries[0]

    tr.run(scenario)


def test_a_tool_with_no_body_is_a_single_line_and_one_with_a_body_folds():
    async def scenario() -> None:
        bare = {"sessionUpdate": "tool_call", "toolCallId": "x", "title": "noop", "status": "completed"}
        rows = [
            support.transcript_row(140.0, bare, tr.DONE),
            support.transcript_row(141.0, support.tool_update("ls", "a.txt"), tr.DONE),
            support.span_row(150.0, "agent_turn", tr.DONE),
        ]
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            group = tr.turns(app)[tr.DONE]
            folded = [c for c in group.query(Collapsible) if c is not group]
            assert len(folded) == 1
            assert "ls" in tr.label(folded[0])
            assert any("noop" in str(s.content) for s in group.query(".entry-tool") if isinstance(s, Static))

    tr.run(scenario)


def test_an_identical_history_skips_the_trail_reconcile(monkeypatch):
    async def scenario() -> None:
        calls: list[int] = []
        original = trail_module.reconcile

        async def counting(*args, **kwargs):
            calls.append(1)
            await original(*args, **kwargs)

        monkeypatch.setattr(trail_module, "reconcile", counting)
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            rows = tr.rows()
            await tr.open_run(app, pilot, link, support.GLOBEX, rows)
            seen = len(calls)
            await tr.push_detail(app, pilot, link, support.GLOBEX, rows)
            assert len(calls) == seen
            await tr.push_detail(app, pilot, link, support.GLOBEX, [*rows, support.log_row(170.0, "new")])
            assert len(calls) == seen + 1

    tr.run(scenario)
