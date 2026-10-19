from __future__ import annotations

import _tui_support as support
import _trail_support as tr
import pytest
from textual.widgets import OptionList, TextArea

from groom import state
from groom.tui.widgets.gate import GateTab
from groom.tui.widgets.lines import PlainLine
from groom.tui.widgets.trail import NO_HISTORY_TEXT, NO_MATCH_TEXT, NO_TELEMETRY_TEXT


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


def test_a_run_without_a_gate_opens_on_trail_and_shows_the_metric_cells():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, tr.rows())
            assert app.pane.tab == "trail"
            assert tr.trail(app).display
            assert not app.query_one(GateTab).display
            metrics = tr.plain(app, "#metrics")
            assert "spans 7" in metrics
            assert "errors 2" in metrics
            assert "[Trail]" in tr.plain(app, "#tabs")

    tr.run(scenario)


def test_a_run_with_a_gate_opens_on_gate_and_t_and_g_switch_tabs():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.ACME, tr.rows())
            assert app.pane.tab == "gate"
            assert app.query_one(GateTab).display
            assert not tr.trail(app).display
            await pilot.press("t")
            assert app.pane.tab == "trail"
            assert tr.trail(app).display
            assert not app.query_one(GateTab).display
            await pilot.press("g")
            assert app.pane.tab == "gate"
            assert app.query_one(GateTab).display

    tr.run(scenario)


def test_a_switches_to_the_gate_tab_before_it_focuses_the_answer_box():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.ACME, tr.rows())
            await pilot.press("t")
            await pilot.press("a")
            assert app.pane.tab == "gate"
            box = app.pane.blocks()[0].answer_box
            assert box is not None
            assert box.has_focus
            await pilot.press(*"gtvK")
            assert box.text == "gtvK"
            assert app.pane.tab == "gate"

    tr.run(scenario)


def test_the_run_head_shows_the_state_node_handle_liveness_and_activity():
    async def scenario() -> None:
        state.WORKFLOWS[support.GLOBEX].activity = tr.HOSTILE
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, tr.rows())
            head = tr.plain(app, "#head")
            assert head.startswith("author-globex")
            assert "running" in head
            assert "node split_stories" in head
            assert support.GLOBEX[:12] in head
            activity = tr.plain(app, "#activity")
            assert activity == "eviltext"

    tr.run(scenario)


def test_v_cycles_the_views_and_the_visible_lines_follow():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, tr.rows())
            assert "[All]" in tr.plain(app, "#trail-bar")
            assert tr.bodies(app) == ["node: 4.0s", "plan · OK · 2.0s", "tests failed", "compiled the plan"]
            assert set(tr.turns(app)) == {tr.DONE, tr.LIVE}
            assert not any(body.startswith("agent_turn") for body in tr.bodies(app))
            await pilot.press("v")
            assert "[Transcript]" in tr.plain(app, "#trail-bar")
            assert "Show:" not in tr.plain(app, "#trail-bar")
            assert tr.bodies(app) == []
            assert set(tr.turns(app)) == {tr.DONE, tr.LIVE}
            await pilot.press("v")
            assert "[Telemetry]" in tr.plain(app, "#trail-bar")
            assert tr.turns(app) == {}
            assert any(body.startswith("agent_turn") for body in tr.bodies(app))
            assert any(body.startswith("plan") for body in tr.bodies(app))
            await pilot.press("v")
            assert "[All]" in tr.plain(app, "#trail-bar")
            assert not any(body.startswith("agent_turn") for body in tr.bodies(app))

    tr.run(scenario)


def test_shift_k_filters_the_telemetry_to_spans():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, tr.rows())
            await pilot.press("K")
            assert "log records" in tr.plain(app, "#trail-bar")
            assert tr.bodies(app) == ["compiled the plan", "tests failed"][::-1]
            await pilot.press("K")
            assert "completed spans" in tr.plain(app, "#trail-bar")
            assert [line.data["kind"] for line in tr.trail(app).query(PlainLine)] == ["span"]
            assert tr.turns(app) == {}
            await pilot.press("v", "v")
            assert [line.data["kind"] for line in tr.trail(app).query(PlainLine)] == ["span", "span"]
            assert tr.turns(app) == {}

    tr.run(scenario)


def test_the_empty_states_say_why_the_trail_is_empty():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, [])
            assert tr.plain(app, "#trail-empty") == NO_HISTORY_TEXT
            await tr.push_detail(app, pilot, link, support.GLOBEX, [support.log_row(100.0, "only a log")])
            assert tr.plain(app, "#trail-empty") == ""
            await pilot.press("K", "K", "K")
            assert tr.plain(app, "#trail-empty") == NO_MATCH_TEXT
            assert tr.children(app) == []

    tr.run(scenario)


def test_a_run_with_no_telemetry_says_so():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
            await app.open_run(support.GLOBEX)
            link.push(support.detail_frame(support.GLOBEX))
            await support.until(lambda: app.store.detail is not None)
            await pilot.pause()
            assert tr.plain(app, "#metrics") == NO_TELEMETRY_TEXT

    tr.run(scenario)


def test_the_view_survives_opening_another_run():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.GLOBEX, tr.rows())
            await pilot.press("v")
            await app.open_run(support.WEBAPP)
            link.push(support.history_frame(support.WEBAPP, tr.rows()))
            await support.until(lambda: app.store.detail is not None)
            await pilot.pause()
            assert "[Transcript]" in tr.plain(app, "#trail-bar")
            assert app.pane.tab == "trail"

    tr.run(scenario)


def test_the_trail_tab_ignores_the_view_key_while_the_gate_tab_is_shown():
    async def scenario() -> None:
        link = support.FakeLink()
        async with tr.booted(link) as (app, pilot):
            await tr.open_run(app, pilot, link, support.ACME, tr.rows())
            await pilot.press("v", "K")
            assert app.store.trail_view == "all"
            assert app.store.trail_kind == ""
            assert isinstance(app.query_one(TextArea), TextArea)

    tr.run(scenario)
