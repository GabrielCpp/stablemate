"""A gRPC call sent through `grpcurl`, which a test stands a fake in for."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

import pytest

from ostler.book import Answer, Bearer, Code, Field, GrpcClient, Int, Object, Rpc, STATUS, Str
from ostler.book.errors import BookError

CREDENTIAL = "s3cret-token"

FAKE = f"""#!{sys.executable}
import json
import os
import sys

symbol = sys.argv[-1]
log = {{"argv": sys.argv[1:], "stdin": sys.stdin.read(), "env": {{k: v for k, v in os.environ.items() if k.startswith("BOOK_GRPC_H")}}}}
with open(os.environ["FAKE_GRPCURL_LOG"], "w") as out:
    json.dump(log, out)
if symbol == "acme.Teams/GetTeam":
    print(json.dumps({{"teamId": "7", "name": "ana", "memberCount": "9007199254740993"}}, indent=2))
elif symbol == "acme.Teams/Missing":
    print(json.dumps({{"code": 5, "message": "no such team", "details": []}}, indent=2), file=sys.stderr)
    sys.exit(64)
else:
    print("Failed to dial target host: connection refused", file=sys.stderr)
    sys.exit(1)
"""

TEAM = Object("Team", team_id=Field(Int()), name=Field(Str()), member_count=Field(Int()))
ASK = Object("Ask", team_id=Field(Int()))


class GetTeam(Rpc):
    rpc = "acme.Teams/GetTeam"
    auth = (Bearer(),)
    body = ASK
    answers = (
        Answer(Code.OK, TEAM, "the team"),
        Answer(Code.NOT_FOUND, STATUS, "no such team"),
        Answer(Code.UNAUTHENTICATED, STATUS, "no credential"),
    )


class Missing(Rpc):
    rpc = "acme.Teams/Missing"
    auth = (Bearer(),)
    body = ASK
    answers = (
        Answer(Code.OK, TEAM, "the team"),
        Answer(Code.NOT_FOUND, STATUS, "no such team"),
        Answer(Code.UNAUTHENTICATED, STATUS, "no credential"),
    )


@pytest.fixture
def grpcurl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "grpcurl"
    script.write_text(FAKE)
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("FAKE_GRPCURL_LOG", str(tmp_path / "log.json"))
    return script


def _logged(grpcurl: Path) -> dict:
    return json.loads((grpcurl.parent / "log.json").read_text())


def test_an_ok_answer_is_read_back_under_the_proto_names(grpcurl: Path):
    client = GrpcClient("teams.local:50051", {Bearer(): CREDENTIAL}, binary=str(grpcurl))
    reply = GetTeam({"team_id": 7}).send(client)
    assert reply.status is Code.OK
    assert reply.body == {"team_id": 7, "name": "ana", "member_count": 9007199254740993}


def test_a_64_bit_integer_that_travels_as_text_is_a_number(grpcurl: Path):
    client = GrpcClient("teams.local:50051", {Bearer(): CREDENTIAL}, binary=str(grpcurl))
    body = GetTeam({"team_id": 7}).send(client).body
    assert isinstance(body, dict)
    assert isinstance(body["member_count"], int)


def test_a_refusal_is_read_from_the_status_the_binary_prints(grpcurl: Path):
    client = GrpcClient("teams.local:50051", {Bearer(): CREDENTIAL}, binary=str(grpcurl))
    reply = Missing({"team_id": 7}).send(client)
    assert reply.status is Code.NOT_FOUND
    assert reply.body == {"message": "no such team"}


def test_the_credential_travels_in_the_environment_and_never_on_the_command_line(grpcurl: Path):
    client = GrpcClient("teams.local:50051", {Bearer(): CREDENTIAL}, binary=str(grpcurl))
    GetTeam({"team_id": 7}).send(client)
    logged = _logged(grpcurl)
    assert CREDENTIAL not in " ".join(logged["argv"])
    assert logged["env"]["BOOK_GRPC_H0"] == f"Bearer {CREDENTIAL}"
    assert "Authorization: ${BOOK_GRPC_H0}" in logged["argv"]
    assert "-expand-headers" in logged["argv"]
    assert json.loads(logged["stdin"]) == {"team_id": 7}


def test_a_missing_binary_is_reported_as_a_book_error(tmp_path: Path):
    client = GrpcClient("teams.local:50051", {Bearer(): CREDENTIAL}, binary=str(tmp_path / "no-grpcurl"))
    with pytest.raises(BookError, match="is not on PATH"):
        GetTeam({"team_id": 7}).send(client)
