"""The input classes of an endpoint that reaches the owner's call: the owner's model predicts, and the endpoint's own refusals stand for what never reaches it."""

from __future__ import annotations

import dataclasses
import sys
import types
from datetime import date
from typing import Any, Iterator, Mapping

import pytest

from ostler.book import (Action, Answer, Done, Endpoint, Enum, Field, Id, Journey, Model, Object, Reaches, Refusal, Refusals, Rule, Service, Str,
                         Diverges)
from ostler.book.check import body_faults, input_faults
from ostler.book.environment import Environment
from ostler.book.domain import Fixture
from ostler.book.inputs import classes, fields_tried, play, predicted, vary
from ostler.book.model import Refused
from ostler.book.owners import Owners

from book_fakes import Plain, Quiet, no_stack
from book_todo import run_book
from test_book_twins import todo_server  # noqa: F401

DAY = date(2026, 11, 4)
OWNER = "acme.owner"
TITLE_MAX = 5
TOO_LONG = Rule("title too long", lambda a, s, by: True)
NO_TICKET = Rule("no such ticket", lambda a, s, by: True)
KNOWN = "known"


class Owned(Model):
    def apply(self, request: Any) -> None:
        if isinstance(request, OwnerFetch):
            if request.path_values()["id"] != KNOWN:
                raise Refused(NO_TICKET)
            return
        title = request.body_value["title"]
        if not title.strip() or len(title) > TITLE_MAX:
            raise Refused(TOO_LONG)

    def rows(self) -> tuple[object, ...]:
        return ()

    def copy(self) -> Owned:
        return Owned(self.today)


class OwnerCreate(Endpoint):
    __module__ = OWNER
    method = "POST"
    path = "/owner/tickets"
    body = Object("OwnerCreate", title=Field(Str(max_len=TITLE_MAX)))
    answers = (Answer(200, None, "made"),)
    carries = Action


class GatewayCreate(Endpoint):
    method = "POST"
    path = "/tickets"
    body = Object("GatewayCreate", title=Field(Str(max_len=TITLE_MAX)))
    answers = (Answer(200, None, "made"), Answer(422, None, "refused"))
    reaches = Reaches(lambda step: OwnerCreate({"title": step.body_value.title}), refused={400: 422})


class Ticket:
    pass


class OwnerFetch(Endpoint):
    __module__ = OWNER
    method = "GET"
    path = "/owner/tickets/{id}"
    params = Object("OwnerFetch", id=Field(Id(Ticket, Str())))
    answers = (Answer(200, None, "found"),)
    carries = Action


class Opens(Journey):
    def steps(self, today: date) -> Iterator[object]:
        yield GatewayCreate({"title": "abc"})


class Gateway(Quiet):
    def __init__(self, strict: bool = True) -> None:
        self.strict = strict

    def perform(self, step: Any) -> Done | Refusal:
        title = step.body_value.get("title") if isinstance(step.body_value, Mapping) else step.body_value.title
        if self.strict and (not isinstance(title, str) or not title.strip() or len(title) > TITLE_MAX):
            return Refusal("bad title", 422)
        return Done()


UNTYPED = Refusals(wrong_type=Refusal("bad title", 422), missing=Refusal("bad title", 422))


def _service(refusals: Refusals = Refusals(), app: Gateway | None = None, *diverges: Diverges) -> Service[Plain]:
    return Service[Plain](name="gateway", new_model=Plain, surface=lambda environment: app or Gateway(), journeys=(Opens,), stack=no_stack,
                          endpoints=(GatewayCreate,), refusals=refusals, diverges=diverges)


@pytest.fixture
def owner(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    held = types.ModuleType(f"{OWNER}.service")
    setattr(held, "service", Service[Owned](name="owner", new_model=Owned, surface=lambda environment: Quiet(), journeys=(), stack=no_stack,
                                  endpoints=(OwnerCreate, OwnerFetch)))
    monkeypatch.setitem(sys.modules, f"{OWNER}.service", held)
    Owners.begin(Environment("local", {}), lambda service: Quiet(), lambda service, surface: service.new_model(DAY))
    yield
    Owners.close()


def _played(service: Service[Plain], app: Gateway) -> dict[str, Any]:
    tried = play(service, app, lambda: Plain(DAY), only=frozenset({"GatewayCreate"}))
    return {s.c.label: s for s in tried.sent}


def test_a_title_the_owner_refuses_is_sent_and_passes_when_the_app_answers_the_mapped_refusal(owner):
    sent = _played(_service(UNTYPED), Gateway())
    assert sent["title too long"].ok, sent["title too long"].note
    assert sent["title blank"].ok, sent["title blank"].note


def test_a_title_the_owner_refuses_fails_when_the_app_accepts_it(owner):
    sent = _played(_service(UNTYPED), Gateway(strict=False))
    assert not sent["title too long"].ok
    assert "422" in sent["title too long"].note


def test_a_class_the_owner_never_sees_passes_on_the_endpoints_own_refusal(owner):
    sent = _played(_service(UNTYPED), Gateway())
    assert sent["title wrong type"].ok, sent["title wrong type"].note
    assert sent["title missing"].ok, sent["title missing"].note


def test_a_class_the_owner_never_sees_fails_when_the_app_accepts_it(owner):
    sent = _played(_service(UNTYPED), Gateway(strict=False))
    assert not sent["title wrong type"].ok


def test_a_class_the_owner_never_sees_is_a_finding_when_the_endpoint_declares_no_refusal_for_it(owner):
    found = [f for f in input_faults(_service()) if f.name == "endpoint GatewayCreate"]
    assert {f.problem.split(":")[0] for f in found} == {"title wrong type", "title missing", "title null"}
    assert all("no wrong_type refusal" in f.problem or "no missing refusal" in f.problem for f in found)


def test_a_class_the_owner_never_sees_is_no_finding_when_the_endpoint_declares_its_refusal(owner):
    assert input_faults(_service(Refusals(wrong_type=Refusal("bad title", 422), missing=Refusal("bad title", 422)))) == []


def test_the_classes_of_the_base_call_are_those_of_the_field_whatever_the_owner_says(owner):
    kinds = {c.kind for c in classes(GatewayCreate({"title": "abc"}), Plain(DAY), None)}
    assert {"too long", "blank", "wrong type", "missing", "null"} <= kinds


def _body(shape: Any) -> type[Endpoint]:
    class Shaped(Endpoint):
        method = "POST"
        path = "/shaped"
        body = Object("Shaped", title=Field(shape))
        answers = (Answer(200, None, "made"),)

    return Shaped


@pytest.mark.parametrize("shape", [Str(max_len=5), Str(format="date"), Str(classes={"short": "a"}), Enum(("a", "b"))])
def test_a_body_field_that_states_a_shape_is_no_finding(shape):
    assert body_faults(Service[Plain](name="x", new_model=Plain, surface=lambda environment: Quiet(), journeys=(), stack=no_stack,
                                      endpoints=(_body(shape),))) == []


def test_a_body_field_of_plain_text_is_a_finding_that_names_what_to_state():
    service = Service[Plain](name="x", new_model=Plain, surface=lambda environment: Quiet(), journeys=(), stack=no_stack,
                            endpoints=(_body(Str()),))
    found = body_faults(service)
    assert [f.name for f in found] == ["endpoint Shaped.title"]
    assert "max_len" in found[0].problem and "classes=" in found[0].problem


def test_the_fields_line_counts_a_body_field_the_run_tried(owner):
    service = _service()
    tried = play(service, Gateway(), lambda: Plain(DAY), only=frozenset({"GatewayCreate"}))
    assert fields_tried(service, tried) == (1, 1)


def test_the_fields_line_is_printed_for_a_book_without_screens(todo_server, tmp_path):  # noqa: F811
    done = run_book(["run", "services.api", "--no-stack", "--out", str(tmp_path)], todo_server.port)
    line = next(line for line in done.stdout.splitlines() if line.startswith("fields: "))
    assert line.endswith(" tried") and " state a shape, " in line


@dataclasses.dataclass
class Asked:
    of: Any
    by: Any
    query: Any


@dataclasses.dataclass(eq=False)
class Draft(Fixture):
    title: str | None = None


class GatewayDrafted(Endpoint):
    method = "POST"
    path = "/drafts"
    body = Object("GatewayDrafted", title=Field(Str(max_len=TITLE_MAX)))
    answers = (Answer(200, None, "made"), Answer(422, None, "refused"))
    reaches = Reaches(lambda step: (lambda s: OwnerCreate({"title": s.of.title}, by=s.by))(Asked(step.given(), step.by, step.query_given)),
                      refused={400: 422})


def test_a_mapping_written_as_a_book_writes_it_sees_the_varied_value_where_it_reads_the_fixture(owner):
    call = GatewayDrafted(Draft(title="abc"))
    assert isinstance(predicted(call, Plain(DAY)), Done)
    kinds = {c.kind: c for c in classes(call, Plain(DAY), None)}
    said = predicted(vary(call, kinds["too long"]), Plain(DAY))
    assert isinstance(said, Refusal) and said.status == 422
    said = predicted(vary(call, kinds["blank"]), Plain(DAY))
    assert isinstance(said, Refusal) and said.status == 422
    assert predicted(vary(call, kinds["missing"]), Plain(DAY)) is None


@dataclasses.dataclass
class Wrapped:
    id: str


@dataclasses.dataclass(eq=False)
class OnWrapped(Fixture):
    record: Any = None

    @property
    def id(self) -> str:
        return self.record.id


class GatewayFetch(Endpoint):
    method = "GET"
    path = "/tickets/{id}"
    params = Object("GatewayFetch", id=Field(Id(Ticket, Str())))
    answers = (Answer(200, None, "found"), Answer(404, None, "missing"))
    reaches = Reaches(lambda step: OwnerFetch({"id": step.of.id}), refused={400: 404})


def test_a_path_the_fixture_computes_from_a_record_takes_the_unknown_id_and_the_owner_refuses_it(owner):
    call = GatewayFetch(OnWrapped(Wrapped(KNOWN)))
    assert isinstance(predicted(call, Plain(DAY)), Done)
    unknown = next(c for c in classes(call, Plain(DAY), None) if c.label == "id unknown")
    varied = vary(call, unknown)
    assert varied.url("http://app") == f"http://app/tickets/{unknown.value}"
    said = predicted(varied, Plain(DAY))
    assert isinstance(said, Refusal) and said.status == 404
