"""The harness side of a gRPC claim: a call through grpcurl, the reply it maps to, and the claim a scenario records."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import pytest

from ostler.qa.harness_host import load_harness_module

harness = load_harness_module("ostler_qa")
grpc = load_harness_module("ostler_qa_grpc")

METHOD = "ticket.v1.TicketService/GetTicket"
ADDRESS = "localhost:50051"

FAKE = '''\
import json, os, sys

log = os.environ["FAKE_GRPCURL_LOG"]
stdin = sys.stdin.read()
with open(log, "w") as sink:
    json.dump({"argv": sys.argv[1:], "stdin": stdin}, sink)
mode = os.environ.get("FAKE_GRPCURL_MODE", "ok")
if mode == "ok":
    print(json.dumps({"ticket": {"id": "T-1", "title": "Printer on fire"}}, indent=2))
elif mode == "stream":
    print(json.dumps({"n": 1}, indent=2))
    print(json.dumps({"n": 2}, indent=2))
elif mode == "window":
    print(json.dumps({"n": 1}, indent=2), flush=True)
    print(json.dumps({"n": 2}, indent=2), flush=True)
    print(json.dumps({"code": 4, "message": "context deadline exceeded"}), file=sys.stderr)
    sys.exit(68)
elif mode == "window-echo":
    print(json.dumps({"note": "token " + os.environ["FAKE_ECHO"]}), flush=True)
    print(json.dumps({"code": 4, "message": "context deadline exceeded " + os.environ["FAKE_ECHO"]}), file=sys.stderr)
    sys.exit(68)
elif mode == "stream-done":
    print(json.dumps({"n": 1}))
elif mode == "refused":
    print(json.dumps({"code": 16, "message": "no credential"}), file=sys.stderr)
    sys.exit(80)
elif mode == "broken":
    print(json.dumps({"n": 1}), flush=True)
    print(json.dumps({"code": 14, "message": "server went away"}), file=sys.stderr)
    sys.exit(78)
elif mode == "not-found":
    print(json.dumps({"code": 5, "message": "no such ticket"}, indent=2), file=sys.stderr)
    sys.exit(69)
elif mode == "echo":
    print(json.dumps({"code": 16, "message": "bad credential " + os.environ["FAKE_ECHO"]}), file=sys.stderr)
    sys.exit(80)
elif mode == "dial":
    print("Failed to dial target host: connection refused " + os.environ.get("FAKE_ECHO", ""), file=sys.stderr)
    sys.exit(1)
'''


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    script = tmp_path / "grpcurl"
    script.write_text(f"#!{sys.executable}\n{FAKE}", encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("FAKE_GRPCURL_LOG", str(tmp_path / "log.json"))
    return script


def _logged(tmp_path: Path) -> dict[str, Any]:
    return json.loads((tmp_path / "log.json").read_text(encoding="utf-8"))


def _call(**extra: Any) -> Any:
    fields: dict[str, Any] = {"address": ADDRESS, "method": METHOD, "request": {"id": "T-1"}}
    fields.update(extra)
    return grpc.Call(**fields)


def test_grpcurl_gets_the_request_on_stdin_and_the_metadata_as_headers(fake: Path, tmp_path: Path) -> None:
    reply = grpc.GrpcurlCaller(str(fake)).call(
        _call(metadata=(("authorization", "Bearer abc"),), deadline=5.0)
    )
    logged = _logged(tmp_path)
    assert logged["argv"] == [
        "-plaintext", "-format-error", "-d", "@", "-H", "authorization: Bearer abc",
        "-max-time", "5.0", ADDRESS, METHOD,
    ]
    assert json.loads(logged["stdin"]) == {"id": "T-1"}
    assert reply.status == "OK"
    assert reply.json() == {"ticket": {"id": "T-1", "title": "Printer on fire"}}


def test_a_stream_prints_one_message_per_object(fake: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "stream")
    reply = grpc.GrpcurlCaller(str(fake)).call(_call())
    assert reply.messages == ({"n": 1}, {"n": 2})
    assert reply.json() == [{"n": 1}, {"n": 2}]


def test_the_numeric_code_on_stderr_maps_to_the_code_name(fake: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "not-found")
    reply = grpc.GrpcurlCaller(str(fake)).call(_call())
    assert (reply.status, reply.message, reply.messages) == ("NOT_FOUND", "no such ticket", ())


def test_a_metadata_value_the_server_echoes_never_reaches_the_reply(
    fake: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "echo")
    monkeypatch.setenv("FAKE_ECHO", "s3cret-token")
    reply = grpc.GrpcurlCaller(str(fake)).call(_call(metadata=(("authorization", "s3cret-token"),)))
    assert reply.status == "UNAUTHENTICATED"
    assert "s3cret-token" not in reply.message


def test_a_call_that_never_reached_the_server_raises_without_the_metadata_value(
    fake: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "dial")
    monkeypatch.setenv("FAKE_ECHO", "s3cret-token")
    with pytest.raises(grpc.GrpcError) as caught:
        grpc.GrpcurlCaller(str(fake)).call(_call(metadata=(("authorization", "s3cret-token"),)))
    assert "dial" in str(caught.value)
    assert "s3cret-token" not in str(caught.value)


def test_a_missing_grpcurl_binary_is_named() -> None:
    with pytest.raises(grpc.GrpcError, match="no-such-grpcurl"):
        grpc.GrpcurlCaller("no-such-grpcurl").call(_call())


def test_a_recorded_caller_answers_from_its_table_and_remembers_the_calls() -> None:
    reply = grpc.Reply("NOT_FOUND", "gone")
    caller = grpc.RecordedCaller({grpc.RecordedCaller.key(METHOD, {"id": "X"}): reply})
    assert caller.call(_call(request={"id": "X"})) is reply
    assert [c.method for c in caller.calls] == [METHOD]
    with pytest.raises(grpc.GrpcError, match="no recorded reply"):
        caller.call(_call(request={"id": "Y"}))


def _qa(tmp_path: Path, caller: Any, emitted: list[dict[str, Any]]) -> Any:
    recorder = harness._Recorder(fd=-1)
    recorder.emit = emitted.append
    return harness.Qa(
        scenario_id="get-ticket",
        target=harness.Target("tickets_grpc", base_url="grpc://localhost:50051"),
        root=tmp_path,
        spec_dir=tmp_path,
        qa_dir=tmp_path / "qa",
        covers=["okf:docs/a.md#get:does:1"],
        recorder=recorder,
        grpc_caller=caller,
    )


def _asserts(emitted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in emitted if record["type"] == "assert"]


def _table() -> Any:
    return grpc.RecordedCaller({
        grpc.RecordedCaller.key(METHOD, {"id": "missing"}): grpc.Reply("NOT_FOUND", "no such ticket"),
        grpc.RecordedCaller.key(METHOD, {"id": "T-1"}): grpc.Reply(
            "OK", "", ({"ticket": {"id": "T-1", "title": "Printer on fire"}},)
        ),
    })


def test_a_recorded_run_passes_the_status_claim_and_the_read_claim(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    qa = _qa(tmp_path, _table(), emitted)
    with qa.claim(["status"]):
        missing = qa.grpc.call(METHOD, {"id": "missing"}, expect_status="NOT_FOUND")
        qa.verify("grpc_status", missing, code="NOT_FOUND", covers=["status"])
    with qa.claim(["read"]):
        found = qa.grpc.call(METHOD, {"id": "T-1"})
        qa.verify("json_path", found.json(), path="ticket.title", equals="Printer on fire", covers=["read"])
    assert [(a["passed"], a["covers"]) for a in _asserts(emitted)] == [(True, ["status"]), (True, ["read"])]
    assert qa.grpc.address == ADDRESS


def test_a_status_claim_naming_the_wrong_code_fails(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    qa = _qa(tmp_path, _table(), emitted)
    with qa.claim(["status"]):
        missing = qa.grpc.call(METHOD, {"id": "missing"}, expect_status="INVALID_ARGUMENT")
        qa.verify("grpc_status", missing, code="INVALID_ARGUMENT", covers=["status"])
    failed = [a for a in _asserts(emitted) if not a["passed"]]
    assert failed
    assert failed[0]["actual"]["status"] == "NOT_FOUND"
    assert failed[0]["expected"] == ["INVALID_ARGUMENT"]
    assert qa.failures >= 1


def test_the_verifier_reads_the_status_a_reply_carries() -> None:
    verify = harness.VERIFIERS["grpc_status"]
    assert verify(grpc.Reply("NOT_FOUND", "x"), {"code": "NOT_FOUND"}).passed is True
    wrong = verify(grpc.Reply("OK", ""), {"code": "NOT_FOUND"})
    assert wrong.passed is False
    assert wrong.actual == {"code": "OK"}
    with pytest.raises(TypeError, match="grpc_status observes a reply"):
        verify(404, {"code": "NOT_FOUND"})


def test_a_declared_secret_resolves_in_metadata_and_stays_out_of_the_records(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(os.environ, "TICKET_TOKEN", "s3cret-token")
    monkeypatch.setitem(harness.REGISTRY.secrets, "TICKET_TOKEN", harness.Secret("TICKET_TOKEN", from_env="TICKET_TOKEN"))
    emitted: list[dict[str, Any]] = []
    caller = _table()
    qa = _qa(tmp_path, caller, emitted)
    with qa.claim(["read"]):
        found = qa.grpc.call(
            METHOD, {"id": "T-1"}, metadata={"authorization": qa.resolve("Bearer $TICKET_TOKEN")},
        )
        qa.verify("json_path", found.json(), path="ticket.id", equals="T-1", covers=["read"])
    assert caller.calls[0].metadata == (("authorization", "Bearer s3cret-token"),)
    assert "s3cret-token" not in json.dumps(emitted)


def test_the_grpc_check_is_in_the_vocabulary() -> None:
    from ostler import checks

    assert "grpc_status" in checks.CHECK_BY_NAME
    assert checks.CHECK_BY_NAME["grpc_status"].observes == "response"


def test_a_stream_the_window_closes_replies_ok_with_the_messages_it_received(
    fake: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "window")
    opened = grpc.GrpcurlCaller(str(fake)).open(_call(request=None), 3.0)
    reply = opened.close()
    assert (reply.status, reply.streamed) == ("OK", True)
    assert reply.messages == ({"n": 1}, {"n": 2})
    assert reply.json() == [{"n": 1}, {"n": 2}]
    logged = _logged(tmp_path)
    assert logged["argv"][-4:-2] == ["-max-time", "3.0"]
    assert json.loads(logged["stdin"]) == {}


def test_a_stream_that_ends_by_itself_replies_ok(fake: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "stream-done")
    reply = grpc.GrpcurlCaller(str(fake)).open(_call(), 3.0).close()
    assert (reply.status, reply.messages, reply.streamed) == ("OK", ({"n": 1},), True)


def test_a_refused_stream_replies_the_refusal_with_no_message(
    fake: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "refused")
    reply = grpc.GrpcurlCaller(str(fake)).open(_call(), 3.0).close()
    assert (reply.status, reply.message, reply.messages, reply.streamed) == (
        "UNAUTHENTICATED", "no credential", (), True,
    )
    assert reply.json() == []


def test_a_stream_that_fails_midway_keeps_the_messages_before_the_failure(
    fake: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "broken")
    reply = grpc.GrpcurlCaller(str(fake)).open(_call(), 3.0).close()
    assert (reply.status, reply.messages) == ("UNAVAILABLE", ({"n": 1},))


def test_a_stream_that_could_not_be_opened_raises(fake: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "dial")
    with pytest.raises(grpc.GrpcError, match="dial"):
        grpc.GrpcurlCaller(str(fake)).open(_call(), 3.0).close()
    with pytest.raises(grpc.GrpcError, match="no-such-grpcurl"):
        grpc.GrpcurlCaller("no-such-grpcurl").open(_call(), 3.0)


def test_a_credential_the_server_echoes_never_reaches_a_streamed_reply(
    fake: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FAKE_GRPCURL_MODE", "window-echo")
    monkeypatch.setenv("FAKE_ECHO", "s3cret-token")
    reply = grpc.GrpcurlCaller(str(fake)).open(_call(metadata=(("authorization", "s3cret-token"),)), 3.0).close()
    assert reply.messages == ({"note": "token [redacted]"},)
    assert "s3cret-token" not in json.dumps(reply.messages) + reply.message


def test_a_streamed_reply_with_no_message_is_an_empty_list() -> None:
    reply = grpc.Reply("OK", "", (), streamed=True)
    assert reply.json() == []
    assert grpc.Reply("OK", "", ({"n": 1},), streamed=True).json() == [{"n": 1}]
    assert grpc.Reply("OK", "", ({"n": 1},)).json() == {"n": 1}


STREAM = "notes.v1.NoteService/Stream"
SEND = "notes.v1.NoteService/Send"


def _stream_table(streamed: Any = None) -> Any:
    reply = streamed or grpc.Reply("OK", "", ({"note": {"title": "hi"}}, {}), streamed=True)
    return grpc.RecordedCaller({
        grpc.RecordedCaller.key(STREAM, None): reply,
        grpc.RecordedCaller.key(SEND, {"title": "hi"}): grpc.Reply("OK", "", ({},)),
        grpc.RecordedCaller.key(SEND, {"title": "bad"}): grpc.Reply("INVALID_ARGUMENT", "no"),
    })


def _stream_client(caller: Any, slept: list[float]) -> Any:
    return grpc.Grpc(ADDRESS, lambda: caller, sleep=slept.append)


def test_the_trigger_is_sent_after_the_stream_opens_and_before_it_closes() -> None:
    caller = _stream_table()
    slept: list[float] = []
    reply = _stream_client(caller, slept).stream(STREAM, during=(SEND, {"title": "hi"}))
    assert caller.events == [("open", STREAM), ("call", SEND), ("close", STREAM)]
    assert [c.method for c in caller.calls] == [STREAM, SEND]
    assert slept == [grpc.STREAM_SETTLE_S]
    assert reply.streamed is True
    assert len(reply.messages) == 2


def test_a_stream_without_a_trigger_only_opens_and_closes() -> None:
    caller = _stream_table()
    _stream_client(caller, []).stream(STREAM)
    assert caller.events == [("open", STREAM), ("close", STREAM)]


def test_the_settle_and_the_window_can_be_chosen() -> None:
    caller = _stream_table()
    slept: list[float] = []
    _stream_client(caller, slept).stream(STREAM, during=(SEND, {"title": "hi"}), settle=0.5, window=4.0)
    assert slept == [0.5]
    assert caller.calls[0].deadline == 4.0


def test_a_failed_trigger_still_closes_the_stream() -> None:
    caller = _stream_table()
    with pytest.raises(grpc.GrpcError, match="INVALID_ARGUMENT"):
        _stream_client(caller, []).stream(STREAM, during=(SEND, {"title": "bad"}))
    assert caller.events == [("open", STREAM), ("call", SEND), ("close", STREAM)]


def test_the_trigger_and_the_stream_carry_the_same_metadata() -> None:
    caller = grpc.RecordedCaller({
        grpc.RecordedCaller.key(STREAM, None): grpc.Reply("OK", "", (), streamed=True),
        grpc.RecordedCaller.key(SEND, {}): grpc.Reply("OK", "", ({},)),
    })
    client = _stream_client(caller, [])
    client.metadata["x-tenant"] = "a"
    client.stream(STREAM, during=(SEND, {}), metadata={"authorization": "Bearer t"})
    assert [c.metadata for c in caller.calls] == [(("x-tenant", "a"), ("authorization", "Bearer t"))] * 2


def test_a_stream_status_the_scenario_did_not_expect_raises_and_one_it_did_passes() -> None:
    refused = grpc.Reply("UNAUTHENTICATED", "no credential", (), streamed=True)
    with pytest.raises(grpc.GrpcError, match="UNAUTHENTICATED"):
        _stream_client(_stream_table(refused), []).stream(STREAM)
    reply = _stream_client(_stream_table(refused), []).stream(STREAM, expect_status="UNAUTHENTICATED")
    assert reply.status == "UNAUTHENTICATED"
    seen: list[tuple[Any, ...]] = []
    client = grpc.Grpc(
        ADDRESS, lambda: _stream_table(refused), sleep=lambda _s: None,
        on_unexpected_status=lambda *args: seen.append(args),
    )
    with pytest.raises(grpc.GrpcError) as caught:
        client.stream(STREAM, expect_status="OK")
    assert caught.value.recorded is True
    assert seen[0][2] == "UNAUTHENTICATED"


def test_the_message_count_verifier_counts_the_messages_a_stream_delivered() -> None:
    verify = harness.VERIFIERS["message_count"]
    reply = grpc.Reply("OK", "", ({"notification": {"title": "hi"}}, {}, {"notification": None}), streamed=True)
    assert verify(reply, {"equals": 3}).passed is True
    assert verify(reply, {"equals": 2}).passed is False
    assert verify(reply, {"at_least": 3}).passed is True
    assert verify(reply, {"at_least": 4}).passed is False
    assert verify(reply, {"path": "notification", "equals": 1}).passed is True
    assert verify(reply, {"path": "notification", "at_least": 2}).passed is False
    missing = verify(reply, {"path": "notification.title", "equals": 0})
    assert missing.passed is False
    assert missing.actual == 1


def test_the_message_count_verifier_counts_a_silent_stream_as_zero() -> None:
    verify = harness.VERIFIERS["message_count"]
    silent = grpc.Reply("OK", "", (), streamed=True)
    assert verify(silent, {"equals": 0}).passed is True
    assert verify(silent, {"path": "notification", "at_least": 1}).passed is False


def test_the_message_count_verifier_refuses_a_unary_reply() -> None:
    verify = harness.VERIFIERS["message_count"]
    unary = grpc.Reply("OK", "", ({"ticket": {}},))
    verdict = verify(unary, {"equals": 1})
    assert verdict.passed is False
    assert "stream" in str(verdict.actual)
    with pytest.raises(TypeError, match="message_count observes a reply"):
        verify(404, {"equals": 1})


def test_a_recorded_run_counts_the_notification_a_trigger_delivered(tmp_path: Path) -> None:
    emitted: list[dict[str, Any]] = []
    qa = _qa(tmp_path, _stream_table(), emitted)
    with qa.claim(["delivered"]):
        seen = qa.grpc.stream(STREAM, during=(SEND, {"title": "hi"}), settle=0)
        qa.verify("message_count", seen, path="note", equals=1, covers=["delivered"])
        qa.verify("json_path", seen.json(), path="[0].note.title", equals="hi", covers=["delivered"])
    assert [a["passed"] for a in _asserts(emitted)] == [True, True]
