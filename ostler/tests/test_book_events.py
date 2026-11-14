"""Events a service emits and hears: declared once, followed by name across books."""

from __future__ import annotations

import gc
import importlib
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator, cast

import pytest

from ostler.book import Action, Answer, Arrange, BookError, Endpoint, Event, Field, Object, Str
from ostler.book.domain import State
from ostler.book.index import cmd_search_book
from ostler.book.search import cmd_explain, items

from test_book_web import _service


class Ping(Endpoint):
    path = "/ping"
    answers = (Answer(200, None, "pong"),)
    does = "Answers pong."


def test_an_event_with_no_docstring_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Silent has no docstring"):

        class Silent(Event):
            name = "ticket.changed"
            detail = Object(actor=Field(Str()))


def test_an_event_with_no_name_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Nameless has no name"):

        class Nameless(Event):
            """Something happened."""

            detail = Object(actor=Field(Str()))


def test_an_event_with_no_detail_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="Empty has no detail"):

        class Empty(Event):
            """Something happened."""

            name = "ticket.changed"


def test_an_outside_event_that_reads_fields_and_hears_no_event_is_refused():
    with pytest.raises(BookError, match="Opens reads .* hears no event"):

        class Opens(Arrange[int]):
            does = "A customer opens a ticket."
            reads = ("ticket_id",)


def test_an_action_that_emits_something_that_is_not_an_event_is_refused():
    with pytest.raises(BookError, match="Transition emits .* not an Event"):

        class Transition(Action):
            emits = cast(Any, ("ticket.changed",))


EMITTER_EVENTS = '''
from ostler.book import Event, Field, Object, Str


class TicketChanged(Event):
    """A ticket's stored record changed."""

    name = "ticket.changed"
    source = "zeta.dynamostream"
    detail = Object(ticket_id=Field(Str()), actor=Field(Str()), snapshot=Field(Object(priority=Field(Str()))))
'''

EMITTER_ACTIONS = '''
from ostler.book import Action

from .events import TicketChanged


class Transition(Action):
    """Moves a ticket to another status."""

    emits = (TicketChanged,)
'''

EMITTER_SERVICE = '''
from ostler.book import Service, Stack
from ostler.book.domain import State

from . import actions
from .events import TicketChanged

service = Service(name="emitter", new_model=State, surface=lambda environment: None, journeys=(),
                  stack=lambda directory: Stack((), directory), events=(TicketChanged,))
'''

LISTENER_SERVICE = '''
from ostler.book import Action, Arrange, Service, Stack
from ostler.book.domain import State
from services.emitter.events import TicketChanged


class Open(Action):
    """Opens a ticket."""


class Opens(Arrange[int]):
    does = "A customer opens a ticket."
    carries = Open
    heard = TicketChanged
    reads = {reads}


service = Service(name="listener", new_model=State, surface=lambda environment: None, journeys=(),
                  stack=lambda directory: Stack((), directory), outside=(Opens,))
'''

FOREIGN_LISTENER_SERVICE = '''
from ostler.book import Action, Arrange, Event, Field, Object, Service, Stack, Str
from ostler.book.domain import State


class TicketChanged(Event):
    """A ticket's stored record changed."""

    name = "ticket.changed"
    owner = "the zeta team"
    detail = Object(ticket_id=Field(Str()))


class Open(Action):
    """Opens a ticket."""


class Opens(Arrange[int]):
    does = "A customer opens a ticket."
    carries = Open
    heard = TicketChanged
    reads = ("ticket_id",)


service = Service(name="listener", new_model=State, surface=lambda environment: None, journeys=(),
                  stack=lambda directory: Stack((), directory), outside=(Opens,), events=(TicketChanged,))
'''


def _write(root: Path, name: str, text: str) -> None:
    path = root / "services" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def _emitter(root: Path, actions: str = EMITTER_ACTIONS) -> None:
    _write(root, "__init__.py", "")
    _write(root, "emitter/__init__.py", "")
    _write(root, "emitter/events.py", EMITTER_EVENTS)
    _write(root, "emitter/actions.py", actions)
    _write(root, "emitter/service.py", EMITTER_SERVICE)


def _listener(root: Path, text: str = LISTENER_SERVICE, reads: str = '("ticket_id", "snapshot.priority")') -> None:
    _write(root, "__init__.py", "")
    _write(root, "listener/__init__.py", "")
    _write(root, "listener/service.py", text.replace("{reads}", reads))


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    saved = {name: loaded for name, loaded in sys.modules.items() if name == "services" or name.startswith("services.")}
    for name in saved:
        del sys.modules[name]
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.chdir(tmp_path)
    importlib.invalidate_caches()
    yield tmp_path
    for name in [n for n in sys.modules if n == "services" or n.startswith("services.")]:
        del sys.modules[name]
    sys.modules.update(saved)
    gc.collect()


def _hits(capsys: pytest.CaptureFixture[str]) -> list[tuple[str, str]]:
    shown = [line.split() for line in capsys.readouterr().out.splitlines() if line and not line.startswith((" ", "="))]
    return sorted((kind, address) for kind, address in shown)


def _search(term: str, kind: str | None = None) -> int:
    return cmd_search_book(SimpleNamespace(service=None, term=term, kind=kind))


def test_an_events_name_finds_its_contract_its_emitter_and_its_listener_across_two_books(root: Path, capsys: pytest.CaptureFixture[str]):
    _emitter(root)
    _listener(root)
    assert _search("ticket.changed") == 0
    assert _hits(capsys) == [("action", "services.emitter.actions:Transition"),
                             ("event", "services.emitter.events:TicketChanged"),
                             ("outside", "services.listener.service:Opens")]


def test_the_event_kind_returns_the_contract_alone(root: Path, capsys: pytest.CaptureFixture[str]):
    _emitter(root)
    _listener(root)
    assert _search("ticket.changed", "event") == 0
    assert _hits(capsys) == [("event", "services.emitter.events:TicketChanged")]


def test_explaining_an_event_names_the_action_that_emits_it_and_the_outside_event_that_hears_it(root: Path, capsys: pytest.CaptureFixture[str]):
    _emitter(root)
    _listener(root)
    service = importlib.import_module("services.emitter.service").service
    assert cmd_explain(service, SimpleNamespace(service="services.emitter", name="TicketChanged")) == 0
    printed = capsys.readouterr().out
    assert "ticket.changed\nsource: zeta.dynamostream\nA ticket's stored record changed.\n" in printed
    assert "emitted by\n    services.emitter.Transition: Moves a ticket to another status.\n" in printed
    assert "heard by\n    services.listener.Opens: A customer opens a ticket.\n" in printed


def test_a_foreign_event_names_its_owner_in_its_contract(root: Path):
    _listener(root, FOREIGN_LISTENER_SERVICE)
    service = importlib.import_module("services.listener.service").service
    [event] = [item for item in items(service, "services.listener") if item.kind == "event"]
    assert event.lines[-1] == "owner: the zeta team"


def test_a_book_with_no_event_keeps_the_index_it_had(module: str):
    service = replace(_service(languages=("en",)), new_model=State, endpoints=(Ping,))
    kinds = {item.kind for item in items(service, module)}
    assert kinds.isdisjoint({"event", "outside"})
    assert not [line for item in items(service, module) for line in item.lines if line.startswith("emits:")]
