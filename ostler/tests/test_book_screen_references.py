"""A screen book that asks its owner's book for the records it shows: the need, the view, the day and the page opened again,
played on the fixture web app and checked against the fixture api book."""

from __future__ import annotations

import importlib
import json
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from book_todo import FIXTURE, edited, module, run_book, services_from
from ostler.book import BookError, Foreign, View
from ostler.book.check import Finding, boundary_faults


@pytest.fixture
def todo_web() -> Iterator:
    app, web = module("app"), module("web.serve")
    api = app.TodoServer().start()
    page = web.WebServer(api.url)
    threading.Thread(target=page.serve_forever, daemon=True).start()
    yield api, page
    api.stop()
    page._server.shutdown()
    page._server.server_close()


@pytest.fixture
def web_chore() -> Iterator:
    with services_from(FIXTURE):
        service = importlib.import_module("services.web.service").service
        yield service, next(axes for axes in service.matrices if axes.record == "chore")


def boundary(module_name: str) -> list[Finding]:
    return boundary_faults(importlib.import_module(f"{module_name}.service").service, module_name)


def test_a_view_holds_the_fields_the_screen_reads_and_fails_a_read_of_any_other():
    record = module("services.api.model.todo").TodoRecord
    view = View(Foreign(record, owner="services.api", reads=("title", "assignee")),
                {"id": "x", "title": "Fix the gate", "assignee": "ana", "description": "secret"})
    assert dict(view) == {"title": "Fix the gate", "assignee": "ana"}
    with pytest.raises(BookError, match="description.*not in the read set"):
        view["description"]


def test_a_view_of_a_row_that_lacks_a_field_the_screen_reads_fails_naming_what_the_owner_has():
    record = module("services.api.model.todo").TodoRecord
    with pytest.raises(BookError, match="has no colour: it has title"):
        View(Foreign(record, owner="services.api", reads=("colour",)), {"title": "Fix the gate"})


def test_the_web_books_overdue_scene_starts_from_a_need_and_holds_no_step_that_moves_the_clock(web_chore):
    from ostler.book import Needs

    service, axes = web_chore
    steps = tuple(axes.scene("overdue").reached_by(axes.today))
    assert len(steps) == 1 and isinstance(steps[0], Needs)
    journey = next(j for j in service.journeys if j.__name__ == "TheDayPasses")
    assert any(isinstance(given, Needs) for given in journey.given)


def test_a_need_in_a_scene_arranges_the_owners_model_alone_and_the_screens_model_takes_the_record_and_the_day(web_chore):
    service, axes = web_chore
    model = axes.scene("overdue").arrange(service.new_model(axes.today))
    [chore] = list(model.todos)
    assert chore.title == "Fix the gate"
    assert chore.status(model.today) == "overdue"
    assert model.today == axes.today + timedelta(days=3)
    assert chore.description is None


def test_the_overdue_state_and_the_journey_that_starts_from_it_play_green_on_the_page(todo_web, tmp_path: Path):
    api, page = todo_web
    done = run_book(["run", "services.web", "--no-stack", "--journey", "TheDayPasses", "--partial", "--out", str(tmp_path / "out")],
                    api.port, web=page.port)
    assert "PASS  TheDayPasses" in done.stdout, done.stdout + done.stderr
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_owners_book_moves_the_clock_five_days_instead_of_three_and_the_web_book_untouched_plays_green(
        todo_web, root: Path, tmp_path: Path):
    api, page = todo_web
    edited(root, "services/api/model/lifecycle.py", "SetClock(Clock(today + timedelta(days=3)))",
           "SetClock(Clock(today + timedelta(days=5)))")
    done = run_book(["run", "services.web", "--no-stack", "--out", str(tmp_path / "out")], api.port, cwd=root, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "8 pass, 0 known defects, 0 fail" in done.stdout
    assert "cells: 41 played on 23 arrangements, 8 impossible, 0 fail" in done.stdout


def test_two_worlds_of_one_play_get_the_same_day_when_the_clock_crosses_midnight(monkeypatch: pytest.MonkeyPatch):
    from datetime import datetime, timezone

    clock = {"at": datetime(2026, 11, 18, 23, 59, tzinfo=timezone.utc)}
    app, surface = module("app"), module("services.web.surface")
    monkeypatch.setattr(app, "now", lambda: clock["at"])
    monkeypatch.setattr(surface, "datetime", SimpleNamespace(now=lambda tz=None: clock["at"]), raising=False)
    api = app.TodoServer().start()
    try:
        web = surface.TodoWeb.__new__(surface.TodoWeb)
        web.backend = surface.Backend(api.url)
        web._shown, web._app_ids = {}, {}

        def world():
            web.backend.reset()
            web.restore()
            return web.backend.today()

        first = world()
        clock["at"] = datetime(2026, 11, 19, 0, 1, tzinfo=timezone.utc)
        second = world()
    finally:
        api.stop()
    assert first == second == datetime(2026, 11, 18).date()


def test_walking_the_overdue_scene_of_the_web_book_arranges_the_need_and_opens_the_page_on_it(todo_web, tmp_path: Path):
    api, page = todo_web
    done = run_book(["walk", "services.web", "--record", "chore", "--scene", "overdue", "--no-stack", "--out", str(tmp_path / "out")],
                    api.port, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "needs TodoRecord of services.api in overdue" in done.stdout
    assert "FAIL" not in done.stdout
    assert [todo.title for todo in api.store.todos] == ["Fix the gate"]


def test_a_field_the_owners_view_lacks_is_named_on_the_screen_books_check(root: Path):
    edited(root, "services/web/foreign.py", 'reads=("title", "due_on", "assignee")', 'reads=("title", "due_on", "colour")')
    [found] = boundary("services.web")
    assert found.blocks
    assert "services.web reads colour of TodoRecord of services.api" in found.problem
    assert "overdue" in found.problem and "title" in found.problem


def test_a_state_the_owner_lacks_is_named_on_the_check_of_a_scene_that_needs_it(root: Path):
    edited(root, "services/web/model/lifecycle.py", 'Needs(TODO, "overdue", ANA)', 'Needs(TODO, "archived", ANA)')
    [found] = boundary("services.web")
    assert found.blocks
    assert found.name == "scene chore:overdue"
    assert "archived" in found.problem and "services.api" in found.problem and "unscheduled" in found.problem


def call(api, method: str, path: str, token: str, body: dict | None = None) -> tuple[int, Any]:
    request = Request(api.url + path, data=None if body is None else json.dumps(body).encode(), method=method,
                      headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urlopen(request) as reply:
            raw = reply.read()
            return reply.status, json.loads(raw) if raw else None
    except HTTPError as reply:
        return reply.code, json.loads(reply.read())


def minted(api, handle: str) -> str:
    account = call(api, "POST", "/admin/persons", "test-token", {"handle": handle})[1]
    return call(api, "POST", "/sign-in", "", {"handle": handle, "password": account["password"]})[1]["token"]


def test_a_person_signs_in_for_a_token_makes_todos_that_are_theirs_and_lists_and_reaches_only_their_own(todo_web):
    api, _ = todo_web
    ana, bo = minted(api, "ana"), minted(api, "bo")
    made = call(api, "POST", "/todos", ana, {"title": "Fix the gate"})[1]
    call(api, "POST", "/todos", "test-token", {"title": "Shared"})
    assert [t["title"] for t in call(api, "GET", "/todos", ana)[1]] == ["Fix the gate"]
    assert [t["title"] for t in call(api, "GET", "/todos", "test-token")[1]] == ["Shared"]
    assert call(api, "GET", f"/todos/{made['id']}", ana)[0] == 200
    for other in (bo, "test-token"):
        assert call(api, "GET", f"/todos/{made['id']}", other) == (404, {"error": "Not found"})
        assert call(api, "DELETE", f"/todos/{made['id']}", other)[0] == 404


def test_a_wrong_password_signs_nobody_in(todo_web):
    api, _ = todo_web
    call(api, "POST", "/admin/persons", "test-token", {"handle": "ana"})
    assert call(api, "POST", "/sign-in", "", {"handle": "ana", "password": "nope"}) == (401, {"error": "Unauthorized"})


def test_the_web_book_plays_signed_in_as_a_person_and_its_todos_are_hers(todo_web, tmp_path: Path):
    api, page = todo_web
    done = run_book(["run", "services.web", "--no-stack", "--journey", "AWeekOfChores", "--partial", "--out", str(tmp_path / "out")],
                    api.port, web=page.port)
    assert done.returncode == 0, done.stdout + done.stderr
    assert {todo.owner for todo in api.store.todos} == {"ana"}
    assert list(api.store.persons) == ["ana"]


def test_the_web_surface_never_wipes_the_apis_store():
    surface = (FIXTURE / "services" / "web" / "surface.py").read_text()
    assert "reset()" not in surface.split("def restore")[1].split("def ")[0]
    assert "backend.reset" not in surface


def test_a_need_naming_a_person_its_scene_does_not_use_is_named_with_the_scenes_actors_on_the_check_and_stops_the_run(
        todo_web, root: Path, tmp_path: Path):
    api, page = todo_web
    edited(root, "services/api/model/lifecycle.py", "(AddTodo(scheduled(today, 2, title=CHORE), by=ANA), SetClock(Clock(today + timedelta(days=3)), by=None))",
           "(AddTodo(scheduled(today, 2, title=CHORE)), SetClock(Clock(today + timedelta(days=3)), by=None))")
    found = boundary("services.web")
    assert {f.name for f in found} == {"journey TheDayPasses", "scene chore:overdue"}
    for each in found:
        assert each.blocks
        assert "no scene takes part for ana" in each.problem and "user" in each.problem
    done = run_book(["run", "services.web", "--no-stack", "--out", str(tmp_path / "out")], api.port, cwd=root, web=page.port)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "no scene takes part for ana" in done.stdout


def test_a_person_who_is_not_in_the_owners_cast_is_named_on_the_check(root: Path):
    edited(root, "services/api/service.py", "cast=(SOLE, ANA),", "cast=(SOLE,),")
    found = boundary("services.web")
    assert found and all(f.blocks for f in found)
    assert any("ana" in f.problem and "not in the cast of services.api" in f.problem for f in found)


def test_a_step_that_names_another_person_signs_the_page_in_as_that_person_first(monkeypatch: pytest.MonkeyPatch):
    from ostler.book import SOLE, Actor
    from ostler.book.owners import Owners

    ana, bo = Actor("ana", fresh="hers"), Actor("bo", fresh="his")
    entered: list = []
    monkeypatch.setattr(Owners, "enter", classmethod(lambda cls, surface, owner, actor: entered.append((owner, actor))))
    monkeypatch.setattr(Owners, "holder", "services.api")
    monkeypatch.setattr(Owners, "standing", ana)
    monkeypatch.setattr(Owners, "signed", ana)
    page = cast(Any, SimpleNamespace(sign_in=lambda account: None))
    left_to_the_world = SimpleNamespace(by=SOLE)
    Owners.play_as(page, left_to_the_world)
    assert left_to_the_world.by == ana and entered == []
    another = SimpleNamespace(by=bo)
    Owners.play_as(page, another)
    assert another.by == bo and entered == [("services.api", bo)]


def hand_seeding_copy(root: Path) -> None:
    edited(root, "services/web/interactions.py", "class SetStore(Interaction[Switch]):",
           'class SeedOverdue(Interaction[Todo]):\n    source = ("web/app.js",)\n    does = "a todo is made behind the page"\n    carries = Add\n\n\n'
           "class SetStore(Interaction[Switch]):")
    edited(root, "services/web/interactions.py", "ALL = (AddTodo,", "ALL = (SeedOverdue, AddTodo,")
    edited(root, "services/web/interactions.py", '__all__ = ["ALL",', '__all__ = ["ALL", "SeedOverdue",')
    edited(root, "services/web/model/lifecycle.py", 'lambda today: (Needs(TODO, "overdue", ANA),)',
           "lambda today: (SeedOverdue(scheduled(today, 2, title=CHORE)), DayPasses(Clock(today + timedelta(days=3))))")
    edited(root, "services/web/model/lifecycle.py", "from ..interactions import AddTodo,", "from ..interactions import SeedOverdue, AddTodo,")


def test_an_act_outside_the_screens_that_makes_a_todo_the_api_stores_is_named_with_the_record_and_the_owners_book(root: Path):
    hand_seeding_copy(root)
    found = [f for f in boundary("services.web") if f.name == "interaction SeedOverdue"]
    [finding] = found
    assert finding.blocks and not finding.told
    assert "TodoRecord" in finding.problem and "services.api" in finding.problem
    assert "outside its screens" in finding.problem


def test_the_same_copy_with_no_foreign_reference_gets_a_note_and_passes(root: Path, monkeypatch: pytest.MonkeyPatch):
    from ostler.book import check

    hand_seeding_copy(root)
    monkeypatch.setattr(check, "references", lambda module, service: [])
    [finding] = [f for f in boundary("services.web") if f.name == "interaction SeedOverdue"]
    assert finding.told and not finding.blocks


def test_a_record_the_screen_book_keeps_and_no_screen_of_it_writes_is_named_with_the_owners_book(root: Path):
    for screen in ("AddForm", "EditForm", "RemoveDialog"):
        edited(root, "services/web/interactions.py", f"    screen = {screen}\n", "")
    found = [f for f in boundary("services.web") if f.name == "record TodoRecord"]
    [finding] = found
    assert finding.blocks
    assert "services.api" in finding.problem and "no screen of it writes" in finding.problem


def test_the_fixture_web_book_keeps_the_todo_its_forms_write_and_the_check_names_nothing(root: Path):
    assert boundary("services.web") == []


def test_the_kit_book_writes_its_todos_through_a_screen_and_the_check_names_nothing(root: Path):
    assert boundary("services.kit") == []
