"""The input classes of a call, and what a declared divergence stands for."""

from __future__ import annotations

from datetime import date
from typing import Any

import json

from ostler.book import Answer, Diverges, Done, Endpoint, Enum, Field, Id, Model, Object, Refusal, Refusals, Service, Str
from ostler.book.http import Client
from ostler.book.httpsurface import HttpSurface
from ostler.book.inputs import InputClass, classes, judge, vary

from book_fakes import Quiet, no_stack

DAY = date(2026, 11, 4)
FIELDS = {"kind": Field(Enum(("a", "b"))), "note": Field(Str(), required=False)}


class Plain(Model):
    def apply(self, request: object) -> None:
        return None

    def rows(self) -> tuple[object, ...]:
        return ()

    def copy(self) -> Plain:
        return Plain(self.today)


class Send(Endpoint):
    method = "POST"
    path = "/send"
    body = Object("Send", **FIELDS)
    answers = (Answer(200, None, "sent"),)


class Team:
    pass


class SendTeam(Endpoint):
    method = "POST"
    path = "/teams"
    body = Object("SendTeam", name=Field(Id(Team, Str(), minted="one cell owns it")))
    answers = (Answer(200, None, "sent"),)


class SendTypedTeam(SendTeam):
    body = Object("SendTypedTeam", name=Field(Id(Team, Str(), strangers="a person chose it")))


class SendTyped(Send):
    typed_wire = True


class Listening(Quiet):
    def __init__(self, answer: Done | Refusal) -> None:
        self.answer = answer

    def perform(self, step: Any) -> Done | Refusal:
        return self.answer


def _kinds(endpoint: type[Endpoint]) -> set[str]:
    return {c.kind for c in classes(endpoint({"kind": "a"}), Plain(DAY), None)}


def _service(*diverges: Diverges) -> Service[Plain]:
    return Service[Plain](name="x", new_model=Plain, surface=lambda environment: Listening(Done()), journeys=(),
                          stack=no_stack, diverges=diverges)


def test_an_untyped_wire_plays_a_wrong_type_an_out_of_enum_and_a_null():
    assert {"wrong type", "out of enum", "null"} <= _kinds(Send)


def test_a_typed_wire_plays_no_wrong_type_no_out_of_enum_and_no_null():
    kinds = _kinds(SendTyped)
    assert not kinds & {"wrong type", "out of enum", "null"}
    assert "missing" in kinds


def test_a_declared_divergence_needs_no_default_refusal():
    chosen = InputClass("body", "kind", "out of enum", "nobody", False, "malformed")
    call = Send({"kind": "nobody"})
    sent = judge(_service(Diverges(Send, "kind out of enum", why="the app takes any kind")), call, chosen, Plain(DAY),
                 Listening(Done()))
    assert sent.ok
    assert sent.diverged is not None
    assert sent.diverged.label == "kind out of enum"


def test_an_undeclared_divergence_with_no_default_refusal_fails():
    chosen = InputClass("body", "kind", "out of enum", "nobody", False, "malformed")
    sent = judge(_service(), Send({"kind": "nobody"}), chosen, Plain(DAY), Listening(Done()))
    assert not sent.ok
    assert "declares no malformed refusal" in sent.note


def _classes_of(endpoint: type[Endpoint]) -> set[str]:
    return {c.kind for c in classes(endpoint({"name": "core"}), Plain(DAY), None)}


def test_a_minted_id_gets_the_input_classes_of_plain_text():
    plain = Object("SendPlain", name=Field(Str()))

    class SendPlain(SendTeam):
        body = plain

    assert _classes_of(SendTeam) == _classes_of(SendPlain)


def test_a_minted_id_gets_none_of_the_id_classes():
    assert not {"unknown", "wrong kind", "another owner's"} & _classes_of(SendTeam)
    assert "malformed" not in _classes_of(SendTeam)


class SendCheckedTeam(SendTeam):
    answers = (Answer(200, None, "sent"), Answer(400, Object("Oops", error=Field(Str())), "refused"))


class NumberRefuser(Client):
    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[int, bytes]:
        name = json.loads(data or b"{}").get("name")
        if isinstance(name, str):
            return 200, b""
        return 400, b'{"error": "name must be text"}'


class Strict(HttpSurface):
    def restore(self) -> None:
        return None

    def rows(self) -> tuple[object, ...]:
        return ()


def test_the_wrong_type_class_of_a_minted_id_field_is_refused_by_a_service_that_refuses_a_number():
    call = SendCheckedTeam({"name": "core"})
    chosen = next(c for c in classes(call, Plain(DAY), None) if c.kind == "wrong type")
    service = Service[Plain](name="x", new_model=Plain, surface=lambda environment: Strict(NumberRefuser("http://x")), journeys=(),
                             stack=no_stack, refusals=Refusals(wrong_type=Refusal("name must be text", 400)))
    sent = judge(service, vary(call, chosen), chosen, Plain(DAY), Strict(NumberRefuser("http://x")))
    assert sent.ok, sent.note
