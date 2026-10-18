from __future__ import annotations

import time

import _attend_support as at
import _attend_ui as ui
import _tui_support as support
import _trail_support as tr
import pytest
from textual.widgets import Collapsible, OptionList

from groom import state
from groom.tui.route import route
from groom.tui.widgets.lines import DividerEntry, MessageEntry, PlainToolEntry, ToolEntry


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


def test_rows_read_status_workflow_reason_when_elapsed_and_node():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            assert ui.ids(screen) == ["j-live", "j-dead", "j-done"]
            live, dead, done = at.prompts(ui.listing(screen))
            assert live.splitlines()[0] == "running  okf-builder"
            assert live.splitlines()[1].startswith("credential wall · ")
            assert live.endswith(" · node await_operator")
            assert done.splitlines() == [
                "completed · exit 0 · blocked  author",
                "stuck on a gate · 2023-11-14 22:13:20 · 1m 30s · node await_operator",
            ]
            assert dead.splitlines() == [
                "completed · exit 1  (unknown workflow)",
                "dead · 2023-11-14 22:15:00 · 1h 5m",
            ]
            assert at.screen_text(screen).count("attend mode: headless") == 1

    tr.run(scenario)


@pytest.mark.parametrize(
    ("started", "ended", "text"),
    [(0, 5, "5s"), (0, 59.4, "59s"), (0, 65, "1m 5s"), (0, 3599, "59m 59s"), (0, 3720, "1h 2m"), (100, 90, "0s")],
)
def test_elapsed_reads_seconds_then_minutes_then_hours(started, ended, text):
    from groom.tui.attend import elapsed

    assert elapsed({"started_at": started, "ended_at": ended}) == text


def test_elapsed_of_a_running_row_runs_to_now():
    from groom.tui.attend import elapsed

    assert elapsed({"started_at": 100.0, "ended_at": None}, now=190.0) == "1m 30s"


def test_opening_fetches_once_and_shows_loading_until_the_reply():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        link.holds[at.SESSIONS] = support.asyncio.Event()
        async with tr.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.main.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("A")
            await support.until(lambda: link.gets == [at.SESSIONS])
            await pilot.pause()
            assert ui.note(app.screen) == "Loading attendances…"
            assert ui.empty(app.screen) == "Select an attendance to read what the agent did."
            link.holds[at.SESSIONS].set()
            await support.until(lambda: ui.listing(app.screen).option_count == 3)
            assert ui.note(app.screen) == ""
            assert link.gets == [at.SESSIONS]

    tr.run(scenario)


def test_no_attendance_and_a_failed_load_say_so():
    async def scenario() -> None:
        link = support.FakeLink()
        await at.serve_sessions(link)
        async with tr.booted(link) as (app, pilot):
            await ui.open_attend(app, pilot, link, rows=0)
            await support.until(lambda: ui.note(app.screen).startswith("No attendance yet"))
            assert ui.note(app.screen) == (
                "No attendance yet. groom has not sent an agent at a parked or dead run."
            )
        failing = support.FakeLink()
        async with tr.booted(failing) as (app, pilot):
            await ui.open_attend(app, pilot, failing, rows=0)
            await support.until(lambda: "Could not load attendances: " in ui.note(app.screen))
            assert ui.note(app.screen).endswith(at.SESSIONS)

    tr.run(scenario)


def test_a_new_rev_refetches_and_keeps_the_highlight_without_loading_text():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            ui.listing(screen).highlighted = ui.ids(screen).index("j-dead")
            at.begin("j-new", "run-blocked", session="s-new", started_at=time.time() + 500)
            await at.serve_sessions(link)
            link.holds[at.SESSIONS] = support.asyncio.Event()
            link.push(support.state_frame())
            await support.until(lambda: link.gets.count(at.SESSIONS) == 2)
            await pilot.pause()
            assert ui.note(screen) == ""
            link.holds[at.SESSIONS].set()
            await support.until(lambda: ui.listing(screen).option_count == 4)
            assert ui.ids(screen)[0] == "j-new"
            assert ui.highlighted(screen) == "j-dead"

    tr.run(scenario)


def test_the_same_rev_does_not_refetch():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            await ui.open_attend(app, pilot, link)
            link.push(support.state_frame())
            link.push(support.state_frame())
            await pilot.pause()
            await pilot.pause()
            assert link.gets == [at.SESSIONS]

    tr.run(scenario)


def test_enter_loads_the_detail_and_renders_each_entry_kind():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await ui.read(pilot, screen, "j-done", link, "s-done")
            await support.until(lambda: len(screen.query("#attend-body > *")) == 7)
            head = at.static(screen, "#attend-head")
            assert head.splitlines() == ["author  run-running  completed", "stuck on a gate", "/runs/run-running"]
            assert at.static(screen, "#attend-resume") == "cd /repo && claude --resume s-done"
            body = list(screen.query("#attend-body > *"))
            assert [type(child) for child in body] == [
                MessageEntry, MessageEntry, ToolEntry, ToolEntry, MessageEntry, DividerEntry, MessageEntry,
            ]
            assert "Reading the **gate** first." in at.widget_text(body[1])
            assert at.title(body[2]) == "Read Read: /runs/r1/docs/gate.md"
            assert "STATUS: AWAITING" in at.widget_text(body[2])
            assert "limit: 40" in at.widget_text(body[2])
            assert at.title(body[3]) == "[red]Bash Bash: false[/red]"
            assert "exit 1" in at.widget_text(body[3])
            assert "Declining" in at.widget_text(body[4])
            assert at.widget_text(body[5]) == "subagent · sub"
            assert "subagent says hi" in at.widget_text(body[6])
            assert ui.empty(screen) == ""

    tr.run(scenario)


def test_a_tool_without_detail_or_result_is_one_plain_line():
    async def scenario() -> None:
        link = support.FakeLink()
        at.begin("j-1", session="s-1")
        at.write_transcript("s-1", [at.turn("assistant", [{"type": "tool_use", "id": "t", "name": "Stop", "input": {}}])])
        await at.serve_sessions(link)
        await at.serve_session(link, "s-1")
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link, rows=1)
            await ui.read(pilot, screen, "j-1", link, "s-1")
            await support.until(lambda: screen.query(PlainToolEntry))
            assert not screen.query(Collapsible)

    tr.run(scenario)


def test_earlier_sessions_are_listed_when_there_is_more_than_one():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await ui.read(pilot, screen, "j-dead", link, "s-b2")
            await support.until(lambda: at.static(screen, "#attend-attempts"))
            assert at.static(screen, "#attend-attempts") == "earlier sessions: s-b1"
            assert ui.empty(screen) == "No transcript on disk for this session yet. It is copied when the agent exits."
            assert not screen.query("#attend-body > *")

    tr.run(scenario)


def test_a_late_reply_for_a_session_the_operator_left_is_dropped():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            slow = route(at.SESSIONS, "s-done")
            link.holds[slow] = support.asyncio.Event()
            ui.listing(screen).highlighted = ui.ids(screen).index("j-done")
            await pilot.press("enter")
            await support.until(lambda: slow in link.gets)
            await ui.read(pilot, screen, "j-live", link, "s-live")
            await support.until(lambda: "working" in at.screen_text(screen))
            link.holds[slow].set()
            await pilot.pause()
            await pilot.pause()
            assert "working" in at.screen_text(screen)
            assert "Declining" not in at.screen_text(screen)
            assert "okf-builder" in at.static(screen, "#attend-head")

    tr.run(scenario)


def test_a_failed_transcript_load_says_why():
    async def scenario() -> None:
        link = support.FakeLink()
        await ui.stock(link)
        del link.get_replies[route(at.SESSIONS, "s-done")]
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link)
            await ui.read(pilot, screen, "j-done", link, "s-done")
            await support.until(lambda: ui.empty(screen).startswith("Could not load this transcript: "))

    tr.run(scenario)


def test_hostile_strings_reach_the_widgets_without_control_bytes():
    async def scenario() -> None:
        link = support.FakeLink()
        at.begin("j-h", workflow=at.HOSTILE, reason=at.HOSTILE, session="s-h", node=at.HOSTILE)
        at.write_transcript("s-h", [
            at.turn("user", at.HOSTILE),
            at.turn("assistant", [
                {"type": "text", "text": at.HOSTILE},
                {"type": "tool_use", "id": "t", "name": "Bash", "input": {"command": at.HOSTILE}},
            ]),
            at.turn("user", [{"type": "tool_result", "tool_use_id": "t", "content": at.HOSTILE, "is_error": True}]),
        ], [at.turn("assistant", [{"type": "text", "text": at.HOSTILE}])])
        await at.serve_sessions(link)
        reply = await at.serve_session(link, "s-h")
        reply["resume"] = at.HOSTILE
        async with tr.booted(link) as (app, pilot):
            screen = await ui.open_attend(app, pilot, link, rows=1)
            await ui.read(pilot, screen, "j-h", link, "s-h")
            await support.until(lambda: len(screen.query("#attend-body > *")) == 5)
            shown = at.screen_text(screen) + "\n".join(at.prompts(ui.listing(screen)))
            assert at.widget_text(screen.query_one("#attend-resume")) == "eviltext"
            assert "eviltext" in shown
            assert not any(ch in shown for ch in at.CONTROLS)
            assert "ZXZpbA" not in shown

    tr.run(scenario)
