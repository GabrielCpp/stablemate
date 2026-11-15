"""A book that names a record its neighbour owns, when the owner speaks gRPC: the neighbour is a gateway over HTTP, the owner a teams service whose calls go out through a fake `grpcurl`."""

from __future__ import annotations

import dataclasses
import json
import stat
import sys
from datetime import date
from pathlib import Path
from typing import Iterator

import pytest

from book_grpc import module
from ostler.book import Code, Environment, GrpcClient, Journey, Needs
from ostler.book.cli import fresh
from ostler.book.owners import Owners
from ostler.book.runner import attempt, walk


Gateway = module("grpcbook.gateway.app").Gateway
GatewayClient = module("grpcbook.gateway.app").GatewayClient
GatewayApi = module("grpcbook.gateway.surface").GatewayApi
TeamsSurface = module("grpcbook.teams.surface").TeamsSurface
ReadGatewayTeam = module("grpcbook.gateway.endpoints").ReadGatewayTeam
TEAM = module("grpcbook.gateway.foreign").TEAM
journeys = module("grpcbook.gateway.journeys")
ATeamIsAtTheGateway = journeys.ATeamIsAtTheGateway
ATeamIsFinishedFromTheGateway = journeys.ATeamIsFinishedFromTheGateway
TheTeamsServiceTurnsACallerAway = journeys.TheTeamsServiceTurnsACallerAway
gateway_service = module("grpcbook.gateway.service").service

FAKE = f"""#!{sys.executable}
import json
import os
import sys

symbol = sys.argv[-1].removeprefix("acme.Teams/")
asked = json.loads(sys.stdin.read() or "{{}}")
path = os.environ["FAKE_TEAMS"]
teams = json.load(open(path)) if os.path.exists(path) else {{"next": 1, "kept": []}}


def refuse(message):
    print(json.dumps({{"code": 5, "message": message, "details": []}}), file=sys.stderr)
    sys.exit(64)


def found():
    return next((t for t in teams["kept"] if t["id"] == asked.get("id")), None)


if symbol == "Add":
    team = {{"id": f"team-{{teams['next']}}", "name": asked.get("name", "")}}
    teams["next"] += 1
    teams["kept"].append(team)
    print(json.dumps(team))
elif symbol == "Get":
    team = found() or refuse("no such team")
    print(json.dumps(team))
elif symbol == "Remove":
    teams["kept"].remove(found() or refuse("no such team"))
    print("{{}}")
elif symbol == "List":
    print(json.dumps({{"teams": teams["kept"]}}))
elif symbol == "Reset":
    teams = {{"next": 1, "kept": []}}
    print("{{}}")
else:
    print("Failed to dial target host: connection refused", file=sys.stderr)
    sys.exit(1)
json.dump(teams, open(path, "w"))
"""

ENVIRONMENT = Environment("local", {"gateway": "http://gateway.local", "teams": "teams.local:50051"})
TODAY = date(2026, 11, 4)


class Kept:
    """The fake owner: the binary the surface sends through, and the teams it holds."""

    def __init__(self, directory: Path):
        self.binary = directory / "grpcurl"
        self.binary.write_text(FAKE)
        self.binary.chmod(self.binary.stat().st_mode | stat.S_IXUSR)
        self.state = directory / "teams.json"

    def client(self) -> GrpcClient:
        return GrpcClient("teams.local:50051", binary=str(self.binary))

    def teams(self) -> list[dict[str, str]]:
        return json.loads(self.state.read_text())["kept"] if self.state.exists() else []


def reached(service, owner: Kept):
    surface = TeamsSurface(ENVIRONMENT, str(owner.binary))
    surface.follow(service.watch)
    return surface


@pytest.fixture
def kept(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kept]:
    owner = Kept(tmp_path)
    monkeypatch.setenv("FAKE_TEAMS", str(owner.state))
    Owners.begin(ENVIRONMENT, lambda service: reached(service, owner), fresh)
    yield owner
    Owners.close()


def gateway(owner: Kept, bug: str | None = None):
    return GatewayApi(GatewayClient(Gateway(owner.client(), bug)))


def played(journey: type[Journey], owner: Kept, bug: str | None = None):
    return walk(journey, gateway_service.new_model(TODAY), gateway(owner, bug))


def failing(result) -> str:
    return " | ".join(step.note for step in result.steps if not step.ok)


def test_a_needed_record_of_a_grpc_owner_is_handed_with_the_id_the_owners_app_issued(kept: Kept):
    needed = Needs(TEAM, "listed")
    done = attempt(needed, gateway_service.new_model(TODAY), gateway(kept))
    assert done.ok, done.note
    assert [team["id"] for team in kept.teams()] == [needed.id]


def test_a_read_that_passes_a_grpc_owners_answer_on_passes_when_the_app_derives_what_the_book_states(kept: Kept):
    result = played(ATeamIsAtTheGateway, kept)
    assert result.ok, failing(result)


def test_the_same_read_fails_with_both_answers_in_the_note_when_the_app_derives_otherwise(kept: Kept):
    result = played(ATeamIsAtTheGateway, kept, "gateway-mislabels")
    assert not result.ok
    note = failing(result)
    assert "the owner answered" in note and '"name": "Ops"' in note
    assert "the app answered" in note and '"label": ""' in note


def test_a_grpc_owners_refusal_comes_back_as_the_book_maps_its_code(kept: Kept):
    result = played(TheTeamsServiceTurnsACallerAway, kept)
    assert result.ok, failing(result)


def test_with_the_gateway_hiding_a_missing_team_the_note_holds_the_code_the_mapped_status_and_the_app_status(kept: Kept):
    result = played(TheTeamsServiceTurnsACallerAway, kept, "gateway-hides-missing")
    assert not result.ok
    note = failing(result)
    assert "NOT_FOUND" in note and "maps it to 404" in note and "the app answered 500" in note


def test_a_code_the_map_does_not_name_fails_the_claim_and_names_the_code(kept: Kept, monkeypatch: pytest.MonkeyPatch):
    passes = dataclasses.replace(ReadGatewayTeam.passes, refused={Code.PERMISSION_DENIED: 403})
    monkeypatch.setattr(ReadGatewayTeam, "passes", passes)
    result = played(TheTeamsServiceTurnsACallerAway, kept)
    assert not result.ok
    note = failing(result)
    assert "NOT_FOUND" in note and "names no such status" in note and "PERMISSION_DENIED" in note


def test_a_write_that_reaches_a_grpc_owners_call_passes(kept: Kept):
    result = played(ATeamIsFinishedFromTheGateway, kept)
    assert result.ok, failing(result)
    assert kept.teams() == []


def test_with_the_gateway_dropping_the_write_the_journey_fails_and_names_the_owners_call(kept: Kept):
    result = played(ATeamIsFinishedFromTheGateway, kept, "gateway-drops-done")
    assert not result.ok
    note = failing(result)
    assert "acme.Teams/Remove" in note and "Ops" in note
