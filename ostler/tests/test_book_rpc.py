"""A gRPC call sent through `grpcurl`, which a test stands a fake in for."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import Any, cast

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


STREAM_ANSWERS = (Answer(Code.OK, TEAM, "each team"),)


def test_a_streaming_rpc_is_declared_with_streams_and_needs_no_answer():
    class WatchTeams(Rpc):
        rpc = "acme.Teams/WatchTeams"
        auth = (Bearer(),)
        body = ASK
        streams = "answer"
        does = "Streams every change of a team."

    assert WatchTeams.streams == "answer"
    assert WatchTeams.answers == ()


def test_a_streams_value_that_is_not_answer_request_or_both_is_refused_where_it_is_declared():
    with pytest.raises(BookError, match="streams is 'sideways'.*answer, request, both"):

        class Bad(Rpc):
            rpc = "acme.Teams/Bad"
            body = ASK
            streams = "sideways"
            answers = STREAM_ANSWERS


def test_a_unary_rpc_still_needs_an_answer():
    with pytest.raises(BookError, match="declares no answer"):

        class NoAnswer(Rpc):
            rpc = "acme.Teams/NoAnswer"
            body = ASK


class WatchOne(Rpc):
    rpc = "acme.Teams/WatchOne"
    body = ASK
    streams = "answer"
    does = "Streams a team."
    source = ("api/teams.proto",)


def test_check_asks_no_matrix_placement_of_a_streaming_rpc():
    from ostler.book.check import matrix_faults
    from test_book_search import _book

    assert [f.name for f in matrix_faults(_book(endpoints=(GetTeam, WatchOne)))] == ["endpoint GetTeam"]


def test_exploration_never_plays_a_streaming_rpc_even_when_it_carries_an_action():
    from ostler.book.explore import attempts, moves

    from ostler.book.domain import Action

    class Move(Action[Any, Any]):
        pass

    class Carried(Rpc):
        rpc = "acme.Teams/Carried"
        body = ASK
        streams = "both"
        carries = Move

    assert moves([Carried])(cast(Any, None)) == []
    assert attempts([Carried], cast(Any, None)) == []


def test_a_run_report_names_each_streaming_rpc_as_not_played():
    from ostler.book.cli import unplayed_lines
    from test_book_search import _book

    assert unplayed_lines(_book(endpoints=(GetTeam, WatchOne))) == [
        "not played: Teams/WatchOne streams its answer, and a run plays calls with one answer"
    ]


def test_search_says_a_call_streams_its_answer():
    from ostler.book.search import items

    [item] = [i for i in items(_book_of(WatchOne), "test_book_rpc") if i.kind == "endpoint"]
    assert "  streams its answer" in item.lines


def test_explain_says_a_call_streams_its_answer(capsys):
    from types import SimpleNamespace

    from ostler.book.search import cmd_explain

    cmd_explain(_book_of(WatchOne), SimpleNamespace(service="test_book_rpc", name="WatchOne"))
    assert "  streams its answer" in capsys.readouterr().out.splitlines()


def _book_of(*endpoints):
    from test_book_search import _book

    return _book(endpoints=endpoints)
