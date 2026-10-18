from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager

import _tui_support as support
import pytest
from textual.pilot import Pilot
from textual.widgets import Markdown, OptionList, Static

from groom import state
from groom.models import GateInfo
from groom.tui.app import GroomTui, GateBlock


@pytest.fixture(autouse=True)
def _fleet():
    support.seed()
    yield
    state.WORKFLOWS.clear()


@asynccontextmanager
async def _booted(link: support.FakeLink) -> AsyncIterator[tuple[GroomTui, Pilot]]:
    app = GroomTui(link)
    async with app.run_test(size=(140, 40)) as pilot:
        yield app, pilot


def _status(app: GroomTui) -> str:
    return str(app.query_one("#status", Static).content)


def _blocks(app: GroomTui) -> list[GateBlock]:
    return app.pane.blocks()


async def _open_blocked(app: GroomTui, pilot: Pilot, link: support.FakeLink) -> GateBlock:
    link.push(support.state_frame())
    await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
    await pilot.press("enter")
    await support.until(lambda: link.sent)
    link.push(support.detail_frame(support.ACME))
    await support.until(lambda: _blocks(app))
    return _blocks(app)[0]


def _run(scenario: Callable[[], Coroutine[None, None, None]]) -> None:
    asyncio.run(scenario())


def test_the_fleet_lists_with_liveness_name_doing_and_a_gate_marker():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, _pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
            listing = app.query_one("#runs", OptionList)
            first = str(listing.get_option_at_index(0).prompt)
            second = str(listing.get_option_at_index(1).prompt)
            assert "coder-acme" in first
            assert "gate" in first
            assert "context/gate.md" in first
            assert "author-globex" in second
            assert "gate" not in second
            assert "live" in _status(app)

    _run(scenario)


def test_opening_a_run_sends_watch_and_shows_the_cleaned_question():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            block = await _open_blocked(app, pilot, link)
            assert link.sent[0] == {"cmd": "watch", "run_id": support.ACME}
            source = block.query_one(Markdown).source
            assert "storage backend" in source
            assert "\x1b" not in source
            assert "\x07" not in source
            assert "ZXZpbA" not in source
            assert "[2J" not in source
            assert block.answer_box is not None

    _run(scenario)


def test_ctrl_s_sends_the_typed_answer_as_an_answer_command():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _open_blocked(app, pilot, link)
            await pilot.press("a")
            await pilot.press(*"sqlite")
            await pilot.press("ctrl+s")
            await support.until(lambda: len(link.sent) == 2)
            assert link.sent[1] == {
                "cmd": "answer",
                "workflow_id": support.ACME,
                "file_path": "context/gate.md",
                "answer": "sqlite",
            }

    _run(scenario)


def test_an_answered_frame_empties_the_box_and_toasts():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            block = await _open_blocked(app, pilot, link)
            await pilot.press("a")
            await pilot.press(*"sqlite")
            assert block.answer_box is not None
            assert block.answer_box.text == "sqlite"
            link.push({"type": "answered", "id": support.ACME, "file_path": "context/gate.md"})
            await support.until(lambda: block.answer_box is not None and block.answer_box.text == "")
            assert any("Answer sent" in n.message for n in app._notifications)

    _run(scenario)


def test_an_answered_frame_for_another_run_leaves_the_box_alone():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            block = await _open_blocked(app, pilot, link)
            await pilot.press("a")
            await pilot.press(*"sqlite")
            link.push({"type": "answered", "id": support.GLOBEX, "file_path": "context/gate.md"})
            link.push({"type": "answered", "id": support.ACME, "file_path": "other.md"})
            await asyncio.sleep(0.2)
            assert block.answer_box is not None
            assert block.answer_box.text == "sqlite"

    _run(scenario)


def test_a_detail_push_mid_typing_keeps_the_half_typed_answer():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            block = await _open_blocked(app, pilot, link)
            await pilot.press("a")
            await pilot.press(*"half")
            state.WORKFLOWS[support.ACME].gates["context/gate.md"].question = "A **new** question"
            link.push(support.detail_frame(support.ACME))
            await support.until(lambda: "new" in block.query_one(Markdown).source)
            assert _blocks(app) == [block]
            assert block.answer_box is not None
            assert block.answer_box.text == "half"
            assert block.answer_box.has_focus

    _run(scenario)


def test_a_failed_send_toasts_an_error_and_keeps_the_text():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            block = await _open_blocked(app, pilot, link)
            await pilot.press("a")
            await pilot.press(*"keepme")
            link.accept_send = False
            await pilot.press("ctrl+s")
            await support.until(lambda: any(n.severity == "error" for n in app._notifications))
            assert block.answer_box is not None
            assert block.answer_box.text == "keepme"

    _run(scenario)


def test_an_empty_answer_is_not_sent():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _open_blocked(app, pilot, link)
            await pilot.press("ctrl+s")
            await support.until(lambda: any("answer first" in n.message for n in app._notifications))
            assert len(link.sent) == 1

    _run(scenario)


def test_a_machine_gate_shows_no_answer_form():
    async def scenario() -> None:
        state.WORKFLOWS[support.GLOBEX].gates["wait.json"] = GateInfo(
            workflow_id=support.GLOBEX, file_path="wait.json", question="build 41", kind="machine"
        )
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
            await app.open_run(support.GLOBEX)
            link.push(support.detail_frame(support.GLOBEX))
            await support.until(lambda: _blocks(app))
            block = _blocks(app)[0]
            assert block.answer_box is None
            assert not block.query("Button")
            assert str(block.query_one(".machine", Static).content) == "Waiting for a machine result."

    _run(scenario)


def test_a_run_with_no_gate_says_nothing_to_answer():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, _pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
            await app.open_run(support.GLOBEX)
            link.push(support.detail_frame(support.GLOBEX))
            await support.until(lambda: "Nothing to answer" in str(app.query_one("#notice", Static).content))
            notice = str(app.query_one("#notice", Static).content)
            assert notice == "Nothing to answer — this run is running at node split_stories."
            assert not _blocks(app)

    _run(scenario)


def test_detail_for_a_run_that_is_not_open_is_ignored():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _open_blocked(app, pilot, link)
            link.push(support.detail_frame(support.GLOBEX))
            await asyncio.sleep(0.2)
            assert [b.file_path for b in _blocks(app)] == ["context/gate.md"]

    _run(scenario)


def test_a_notify_frame_raises_a_cleaned_notification_and_rings_the_bell(monkeypatch):
    async def scenario() -> None:
        link = support.FakeLink()
        rung: list[int] = []
        async with _booted(link) as (app, _pilot):
            monkeypatch.setattr(app, "bell", lambda: rung.append(1))
            link.push({"type": "notify", "message": "coder-acme needs you\x1b]52;c;AAAA\x07\x1b[2J"})
            await support.until(lambda: app._notifications)
            messages = [n.message for n in app._notifications]
            assert messages == ["coder-acme needs you"]
            assert rung == [1]

    _run(scenario)


def test_a_failed_watch_falls_back_to_the_worker_endpoint():
    async def scenario() -> None:
        link = support.FakeLink()
        link.accept_send = False
        link.get_replies[f"/worker/{support.ACME}"] = support.detail_frame(support.ACME)["detail"]
        async with _booted(link) as (app, pilot):
            link.push(support.state_frame())
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
            await pilot.press("enter")
            await support.until(lambda: _blocks(app))
            assert link.gets == [f"/worker/{support.ACME}"]

    _run(scenario)


def test_j_and_k_move_the_run_list_cursor():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            link.push(support.state_frame())
            listing = app.query_one("#runs", OptionList)
            await support.until(lambda: listing.option_count == 3)
            await support.until(lambda: listing.highlighted == 0)
            await pilot.press("j")
            assert listing.highlighted == 1
            await pilot.press("k")
            assert listing.highlighted == 0

    _run(scenario)


def test_the_cursor_follows_its_run_when_the_order_changes():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            link.push(support.state_frame())
            listing = app.query_one("#runs", OptionList)
            await support.until(lambda: listing.option_count == 3)
            await support.until(lambda: listing.highlighted == 0)
            await pilot.press("j")
            state.upsert_workflow(
                "initech12345", name="aaa-first", workflow_type="coder", run_id="run-new"
            )
            link.push(support.run_frame("initech12345"))
            await support.until(lambda: listing.option_count == 4)
            assert listing.highlighted is not None
            assert listing.get_option_at_index(listing.highlighted).id == support.GLOBEX

    _run(scenario)


def test_an_empty_fleet_says_nothing_is_running_and_scanning_says_discovering():
    async def scenario() -> None:
        state.WORKFLOWS.clear()
        link = support.FakeLink()
        async with _booted(link) as (app, _pilot):
            link.push(support.state_frame())
            await support.until(lambda: "No workhorse runs — nothing is running." in _status(app))
            state.SCANNING = True
            link.push(support.state_frame())
            await support.until(lambda: "Discovering containers…" in _status(app))
            state.SCANNING = False

    _run(scenario)


def test_the_app_starts_against_a_down_server_resyncs_over_http_and_recovers():
    async def scenario() -> None:
        link = support.FakeLink()
        link.fail_open = True
        link.get_replies["/api/state"] = support.state_frame()
        async with _booted(link) as (app, _pilot):
            assert "reconnecting" in _status(app)
            app.evaluate()
            await support.until(lambda: app.query_one("#runs", OptionList).option_count == 3)
            assert link.gets == ["/api/state"]
            assert "reconnecting" in _status(app)
            link.fail_open = False
            await support.until(lambda: link.opens == 1, timeout=10)
            app.evaluate()
            assert "live" in _status(app)

    _run(scenario)


def test_a_dropped_socket_reconnects_and_resends_watch_for_the_open_run():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            await _open_blocked(app, pilot, link)
            link.drop()
            await support.until(lambda: link.opens == 2, timeout=10)
            await support.until(lambda: len(link.sent) == 2)
            assert link.sent[1] == {"cmd": "watch", "run_id": support.ACME}

    _run(scenario)


def test_r_posts_a_refresh():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (_app, pilot):
            await pilot.press("r")
            await support.until(lambda: link.posts == ["/refresh"])

    _run(scenario)


def test_typing_the_binding_keys_into_the_answer_box_does_not_trigger_them():
    async def scenario() -> None:
        link = support.FakeLink()
        async with _booted(link) as (app, pilot):
            block = await _open_blocked(app, pilot, link)
            await pilot.press("a")
            await pilot.press(*"jkqra")
            assert block.answer_box is not None
            assert block.answer_box.text == "jkqra"
            assert link.posts == []

    _run(scenario)
