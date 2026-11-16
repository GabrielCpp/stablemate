"""A credential that signs an account in again as its token nears its end, and the play that needs it."""

from __future__ import annotations

import base64
import json
import urllib.request
from typing import Any, Iterator

import pytest

from ostler.book import Answer, Bearer, Code, Environment, GrpcClient, Rpc, STATUS, Signed
from ostler.book.cast import SOLE
from ostler.book.runner import walk

from book_todo import module

TodoApi = module("services.api.surface").TodoApi
service = module("services.api.service").service
journeys = module("services.api.journeys")


class Clock:
    def __init__(self, at: float = 1_000_000.0) -> None:
        self.at = at

    def __call__(self) -> float:
        return self.at

    def advance(self, seconds: float) -> None:
        self.at += seconds


def jwt(exp: object) -> str:
    def part(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return ".".join([part({"alg": "none"}), part({"exp": exp}), "signature"])


class Mint:
    def __init__(self, clock: Clock, life: float | None = None) -> None:
        self.clock = clock
        self.life = life
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        if self.life is None:
            return f"opaque-{self.count}"
        return jwt(self.clock() + self.life)


def test_a_jwt_within_the_margin_of_its_exp_is_signed_in_again():
    clock = Clock()
    mint = Mint(clock, life=600)
    signed = Signed(mint, margin=300, clock=clock)
    first = signed.token
    clock.advance(299)
    assert signed.token == first
    clock.advance(2)
    assert signed.token != first
    assert mint.count == 2


def test_a_jwt_with_life_left_is_kept():
    clock = Clock()
    mint = Mint(clock, life=3600)
    signed = Signed(mint, clock=clock)
    first = signed.token
    clock.advance(3000)
    assert signed.token == first
    assert mint.count == 1


def test_an_opaque_token_is_signed_in_again_after_lasts():
    clock = Clock()
    mint = Mint(clock)
    signed = Signed(mint, lasts=600, margin=100, clock=clock)
    first = signed.token
    clock.advance(499)
    assert signed.token == first
    clock.advance(2)
    assert signed.token == "opaque-2"


def test_an_opaque_token_with_no_lasts_is_never_signed_in_again():
    clock = Clock()
    mint = Mint(clock)
    signed = Signed(mint, clock=clock)
    first = signed.token
    clock.advance(10_000_000)
    assert signed.token == first
    assert mint.count == 1


def test_a_token_with_a_non_numeric_exp_is_read_as_opaque():
    clock = Clock()
    signed_in: list[str] = []

    def sign() -> str:
        signed_in.append("x")
        return jwt("soon")

    signed = Signed(sign, lasts=60, margin=10, clock=clock)
    signed.token
    clock.advance(49)
    signed.token
    assert len(signed_in) == 1
    clock.advance(2)
    signed.token
    assert len(signed_in) == 2


def test_a_credential_signs_in_on_its_first_read_and_not_before():
    mint = Mint(Clock())
    signed = Signed(mint)
    assert mint.count == 0
    assert str(signed) == "opaque-1"
    assert mint.count == 1


def test_the_repr_hides_the_token():
    signed = Signed(lambda: "s3cret-token")
    assert "s3cret-token" not in repr(signed)
    signed.token
    assert "s3cret-token" not in repr(signed)


@pytest.fixture
def clock() -> Clock:
    return Clock(float(1_800_000_000))


@pytest.fixture
def app(clock: Clock) -> Iterator[Any]:
    server = module("app").TodoServer(sign_in=True, clock=clock).start()
    yield server
    server.stop()


def sign_in(app: Any) -> str:
    with urllib.request.urlopen(urllib.request.Request(f"{app.url}/sign-in", data=b"{}", method="POST")) as reply:
        return json.loads(reply.read())["token"]


def surface_holding(app: Any, credential: Any) -> Any:
    surface = TodoApi(Environment("local", {"api": app.url}))
    surface.client.held.clear()
    surface.client.hold(SOLE, Bearer(), credential)
    surface.follow(service.watch)
    return surface


def play(app: Any, credential: Any, clock: Clock) -> list[Any]:
    surface = surface_holding(app, credential)
    results = []
    for journey in (journeys.ClearTheList, journeys.AWeekOfChores):
        surface.reset()
        results.append(walk(journey, service.new_model(surface.today()), surface))
        clock.advance(7200)
    return results


def refused(result: Any) -> str:
    return " | ".join(step.note for step in result.steps if not step.ok)


def test_a_signed_standing_account_plays_a_second_journey_after_its_token_expired(app, clock):
    first, second = play(app, Signed(lambda: sign_in(app), clock=clock), clock)
    assert first.ok, refused(first)
    assert second.ok, refused(second)


def test_a_bare_token_standing_account_is_refused_with_401_once_its_token_expired(app, clock):
    first, second = play(app, sign_in(app), clock)
    assert first.ok, refused(first)
    assert not second.ok
    assert "401" in refused(second)


class Hears(GrpcClient):
    def __init__(self, base: str, credentials: Any) -> None:
        super().__init__(base, credentials)
        self.sent: list[str] = []

    def transport(self, method: str, url: str, headers: dict[str, str], data: bytes | None) -> Any:
        self.sent.append(headers["Authorization"])
        return Code.OK, b""


class Ping(Rpc):
    rpc = "acme.Teams/Ping"
    auth = (Bearer(),)
    answers = (Answer(Code.OK, None, "pong"), Answer(Code.UNAUTHENTICATED, STATUS, "no credential"))


def test_a_grpc_client_reads_a_signed_credential_at_each_call(clock):
    mint = Mint(clock, life=600)
    client = Hears("teams.local:50051", {Bearer(): Signed(mint, clock=clock)})
    client.send(Ping())
    clock.advance(400)
    client.send(Ping())
    first, second = client.sent
    assert first != second
    assert mint.count == 2
