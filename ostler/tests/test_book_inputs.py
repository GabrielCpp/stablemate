"""The input classes of a call, and what a declared divergence stands for."""

from __future__ import annotations

from datetime import date
from typing import Any

from ostler.book import Answer, Diverges, Done, Endpoint, Enum, Field, Model, Object, Refusal, Service, Str
from ostler.book.inputs import InputClass, classes, judge

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
