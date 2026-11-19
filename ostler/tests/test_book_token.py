"""A page token the model keeps and the app issues another for: compared by presence, translated on send, tried as a made up value."""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator

from ostler.book import (Action, Answer, Client, Collection, Create, Endpoint, Field, Fixture, Int, Journey, List, Object, Rule, Service, Show,
                         State, Str, Token, Unique)
from ostler.book.check import token_faults
from ostler.book.http import Identities, Witness
from ostler.book.httpsurface import HttpSurface
from ostler.book.inputs import classes, judge, vary
from ostler.book.runner import walk
from ostler.book.witness import report

from book_fakes import no_stack

DAY = date(2026, 11, 4)
TITLES = ("one", "two", "three")
PAGE = Token("row page")
ROW = Object("RowOut", title=Field(Str()))
ROW_PAGE = Object("RowPage", rows=Field(List(ROW)), next_page_token=Field(PAGE, required=False, nullable=True))
LIST_IN = Object("ListRows", page_size=Field(Int(), required=False), page_token=Field(PAGE, required=False))
OOPS = Object("Oops", error=Field(Str()))


@dataclass
class Row:
    title: str


@dataclass(frozen=True)
class RowOut:
    title: str


@dataclass(frozen=True)
class Shown:
    rows: tuple[RowOut, ...]
    next_page_token: str


@dataclass(eq=False)
class Listing(Fixture):
    page_size: int | None = None
    page_token: str | None = None


class Shelf(State):
    kept = Collection(Row, Unique("title"))

    def rows(self) -> tuple[object, ...]:
        return ()


def after(token: str | None) -> int | None:
    if not token:
        return 0
    return int(token[6:]) if token.startswith("after:") and token[6:].isdigit() else None


bad_token = Rule[Listing, Shelf]("invalid page token", lambda a, s, by: after(a.page_token) is None, 400)


class ListRows(Action[Listing, Shelf]):
    accept = Listing
    rules = (bad_token,)

    @staticmethod
    def reduce(a: Listing, s: Shelf, by: Any) -> Show:
        start, size = after(a.page_token) or 0, a.page_size or 10
        held = list(s.kept)
        end = start + size
        return Show(Shown(tuple(RowOut(r.title) for r in held[start:end]), f"after:{end}" if end < len(held) else ""))


class ListEndpoint(Endpoint):
    method = "POST"
    path = "/rows/list"
    body = LIST_IN
    answers = (Answer(200, ROW_PAGE, "a page of rows"), Answer(400, OOPS, "the token is not one the service gave"))
    carries = ListRows
    does = "Lists the rows a page at a time."


def shelf(today: date) -> Shelf:
    model = Shelf(today)
    for title in TITLES:
        Create(Shelf.kept, Row(title)).apply(model)
    return model


class FakeApp(Client):
    """A service whose tokens are base64 of an offset; `bug` names what it gets wrong."""

    def __init__(self, bug: str = "") -> None:
        super().__init__("http://rows.test")
        self.bug = bug
        self.received: list[dict[str, Any]] = []

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> tuple[int, bytes]:
        sent = json.loads(data or b"{}")
        self.received.append(sent)
        token = sent.get("page_token")
        try:
            start = int(base64.b64decode(token).decode()) if token else 0
        except ValueError:
            start = -1
        if start < 0 and self.bug != "accepts":
            return 400, b'{"error": "invalid page token"}'
        start = max(start, 0)
        if self.bug == "skips" and start:
            start += 1
        end = start + sent.get("page_size", 10)
        body: dict[str, Any] = {"rows": [{"title": t} for t in TITLES[start:end]]}
        last = end >= len(TITLES)
        if (end < len(TITLES) and not (self.bug == "drops" and start == 1)) or (last and self.bug == "keeps"):
            body["next_page_token"] = base64.b64encode(str(end).encode()).decode()
        return 200, json.dumps(body).encode()


class ShelfSurface(HttpSurface):
    def restore(self) -> None:
        return None

    def rows(self) -> tuple[object, ...]:
        return ()


class ThreePages(Journey):
    """A reader follows the rows a page at a time."""

    def steps(self, today: date) -> Iterator[object]:
        yield ListEndpoint(Listing(page_size=1))
        yield ListEndpoint(Listing(page_size=1, page_token="after:1"))
        yield ListEndpoint(Listing(page_size=1, page_token="after:2"))


class StrangerToken(Journey):
    """A reader sends a token nothing issued."""

    def steps(self, today: date) -> Iterator[object]:
        yield ListEndpoint(Listing(page_size=1, page_token="after:2"))


def played(journey: type[Journey], bug: str = "") -> tuple[Any, FakeApp]:
    app = FakeApp(bug)
    return walk(journey, shelf(DAY), ShelfSurface(app)), app


def test_three_calls_with_a_page_of_one_pass_and_the_app_gets_its_own_token():
    result, app = played(ThreePages)
    assert result.ok, [step.note for step in result.steps]
    first, second, third = app.received
    assert "page_token" not in first
    assert base64.b64decode(second["page_token"]) == b"1"
    assert base64.b64decode(third["page_token"]) == b"2"


def test_a_token_on_the_last_page_fails_with_the_presence_wording():
    result, _ = played(ThreePages, "keeps")
    assert not result.ok
    assert ".next_page_token: the app gave a token and the model says there is no next page" in result.steps[-1].note


def test_no_token_on_a_middle_page_fails_with_the_presence_wording():
    result, _ = played(ThreePages, "drops")
    assert not result.ok
    assert ".next_page_token: the model says there is a next page and the app gave no token" in result.steps[1].note


def test_a_row_skipped_at_a_page_edge_fails_on_the_rows():
    result, _ = played(ThreePages, "skips")
    assert not result.ok
    assert "rows[0]" in result.steps[1].note


def test_a_token_never_learned_goes_out_as_written():
    ids = Identities()
    sent = ListEndpoint(Listing(page_token="after:7")).payload(ids)
    assert sent == {"page_token": "after:7"}
    ids.learn_token("row page", "after:7", "N")
    assert ListEndpoint(Listing(page_token="after:7")).payload(ids) == {"page_token": "N"}


def test_a_blank_token_sends_nothing():
    assert ListEndpoint(Listing(page_size=1, page_token="")).payload(Identities()) == {"page_size": 1}


def test_a_learned_token_is_forgotten_with_the_ids():
    ids = Identities()
    ids.learn_token("row page", "after:1", "MQ==")
    ids.clear()
    assert ids.real_token("row page", "after:1") is None


def test_a_token_request_field_gets_the_made_up_class_and_none_of_the_text_classes():
    found = classes(ListEndpoint(Listing(page_size=1, page_token="after:1")), shelf(DAY), None)
    tokens = [c for c in found if c.name == "page_token"]
    assert [(c.kind, c.value, c.default, c.valid) for c in tokens if c.place == "body" and c.kind == "made up"] == [
        ("made up", "not-a-token", "malformed", False)]
    assert not {c.kind for c in tokens} & {"blank", "too long"}


def _service(app: FakeApp) -> Service[Shelf]:
    return Service[Shelf](name="rows", new_model=shelf, surface=lambda environment: ShelfSurface(app), journeys=(ThreePages,), stack=no_stack,
                         endpoints=(ListEndpoint,))


def _made_up(bug: str):
    app = FakeApp(bug)
    call = ListEndpoint(Listing(page_size=1, page_token="after:1"))
    chosen = next(c for c in classes(call, shelf(DAY), None) if c.kind == "made up")
    return judge(_service(app), vary(call, chosen), chosen, shelf(DAY), ShelfSurface(app))


def test_the_made_up_token_passes_when_the_app_refuses_it():
    sent = _made_up("")
    assert sent.ok, sent.note


def test_the_made_up_token_fails_when_the_app_accepts_it():
    assert not _made_up("accepts").ok


class Issuer(Endpoint):
    path = "/issue"
    answers = (Answer(200, Object("Issued", next=Field(Token("page"))), "a page"),)


class Taker(Endpoint):
    path = "/take"
    query = Object("TakerQuery", after=Field(Token("elsewhere"), required=False))
    answers = (Answer(200, None, "taken"),)


class OpaqueIssuer(Endpoint):
    path = "/opaque"
    answers = (Answer(200, Object("Opaque", next=Field(Token("page"), opaque="the app makes it")), "a page"),)


def _checked(*endpoints: type[Endpoint]) -> list[str]:
    service = Service[Shelf](name="rows", new_model=shelf, surface=lambda environment: ShelfSurface(FakeApp()), journeys=(), stack=no_stack,
                             endpoints=endpoints)
    return [str(f) for f in token_faults(service)]


def test_a_request_token_no_answer_issues_is_a_finding():
    assert _checked(Issuer, Taker) == ["endpoint Taker: query after: no answer issues the token elsewhere"]


def test_a_request_token_an_answer_issues_is_silent():
    assert _checked(ListEndpoint) == []


def test_an_opaque_answer_token_is_a_finding():
    assert _checked(OpaqueIssuer) == ["endpoint OpaqueIssuer: answer 200 next: a typed token is compared by presence and needs no opaque"]


def _witnessed(*tokens: str) -> list[str]:
    seen = Witness()
    answer = ListEndpoint.answers[0]
    for token in tokens:
        seen.see(ListEndpoint, answer, {"rows": [{"title": "one"}], "next_page_token": token})
    gaps = report([ListEndpoint], seen).gaps
    return [p for gap in gaps for paths in gap.fields.values() for p in paths]


def test_a_token_field_is_seen_once_any_answer_held_a_token():
    assert "next_page_token" not in _witnessed("MQ==", "")


def test_an_empty_last_page_token_alone_leaves_the_field_unseen_but_a_token_earlier_clears_it():
    assert "next_page_token" in _witnessed("")
    assert _witnessed("MQ==", "") == []
