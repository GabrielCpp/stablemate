"""OpenCode's ``run --format json`` events mapped to ACP updates, over one recorded turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner.backends.opencode import OpenCodeBackend, OpenCodeTranscript

FIXTURE = Path(__file__).parent / "fixtures" / "opencode_turn.jsonl"


def _events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _all() -> list[acp.MappedUpdate]:
    mapper = OpenCodeTranscript()
    return [update for event in _events() for update in mapper.updates(event)]


def _kind(update: acp.MappedUpdate) -> str:
    return update.update["sessionUpdate"]


def _tools() -> list[dict[str, Any]]:
    return [e["part"] for e in _events() if e["type"] == "tool_use"]


def _tool(name: str, status: str = "completed") -> dict[str, Any]:
    return next(p for p in _tools() if p["tool"] == name and p["state"]["status"] == status)


def _calls() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call"}


def _results() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call_update"}


def test_the_backend_hands_out_a_fresh_opencode_mapper_per_turn():
    backend = OpenCodeBackend()
    first = backend.transcript_mapper()
    assert isinstance(first, OpenCodeTranscript)
    assert backend.transcript_mapper() is not first


def test_the_session_id_comes_from_any_event():
    mapper = OpenCodeTranscript()
    event = _events()[0]
    assert mapper.updates(event) == []
    assert mapper.session_id == event["sessionID"]


def test_every_tool_call_has_one_matching_update():
    calls = [u.update["toolCallId"] for u in _all() if _kind(u) == "tool_call"]
    results = [u.update["toolCallId"] for u in _all() if _kind(u) == "tool_call_update"]
    assert calls
    assert sorted(results) == sorted(calls)
    assert len(set(calls)) == len(calls)


def test_tool_calls_carry_input_title_and_kind():
    calls = _calls()
    for part in _tools():
        if part["tool"] == "todowrite":
            continue
        call = calls[part["callID"]]
        assert call["rawInput"] == part["state"]["input"]
        assert call["title"].startswith(part["tool"])
        assert call["status"] == "in_progress"
    assert calls[_tool("read")["callID"]]["kind"] == "read"
    assert calls[_tool("bash", "completed")["callID"]]["kind"] == "execute"
    assert calls[_tool("edit")["callID"]]["kind"] == "edit"


def test_an_edit_carries_its_diff_on_the_call_and_again_on_the_result():
    part = _tool("edit")
    state = part["state"]
    diff = {
        "type": "diff",
        "path": state["input"]["filePath"],
        "oldText": state["input"]["oldString"],
        "newText": state["input"]["newString"],
    }
    call = _calls()[part["callID"]]
    result = _results()[part["callID"]]
    assert call["content"] == [diff]
    assert call["locations"] == [{"path": state["input"]["filePath"]}]
    assert result["content"] == [diff, acp.text_item(state["output"])]


def test_a_write_is_a_new_file_diff():
    mapper = OpenCodeTranscript()
    event = {
        "type": "tool_use",
        "sessionID": "s",
        "part": {
            "type": "tool",
            "tool": "write",
            "callID": "w",
            "state": {"status": "completed", "input": {"filePath": "/work/a", "content": "hi"}, "output": "ok"},
        },
    }
    call, _result = mapper.updates(event)
    assert call.update["kind"] == "edit"
    assert call.update["content"] == [{"type": "diff", "path": "/work/a", "oldText": None, "newText": "hi"}]


def test_a_result_carries_the_tool_output():
    part = _tool("read")
    assert _results()[part["callID"]]["content"] == [acp.text_item(part["state"]["output"])]
    assert _results()[part["callID"]]["status"] == "completed"


def test_an_errored_tool_is_failed_and_shows_its_error():
    part = _tool("read", "error")
    result = _results()[part["callID"]]
    assert result["status"] == "failed"
    assert result["content"] == [acp.text_item(part["state"]["error"])]


def test_a_command_with_a_non_zero_exit_is_failed():
    results = _results()
    failed = [p for p in _tools() if p["tool"] == "bash" and p["state"]["metadata"]["exit"]]
    done = [p for p in _tools() if p["tool"] == "bash" and not p["state"]["metadata"]["exit"]]
    assert failed
    assert done
    assert all(results[p["callID"]]["status"] == "failed" for p in failed)
    assert all(results[p["callID"]]["status"] == "completed" for p in done)


def test_a_todowrite_becomes_a_plan_not_a_tool_call():
    part = _tool("todowrite")
    plans = [u.update for u in _all() if _kind(u) == "plan"]
    assert len(plans) == 1
    assert plans[0]["entries"] == [
        {"content": t["content"], "priority": t["priority"], "status": t["status"]}
        for t in part["state"]["input"]["todos"]
    ]
    assert part["callID"] not in _calls()
    assert part["callID"] not in _results()


def test_reasoning_and_text_become_chunks():
    thoughts = [u.update for u in _all() if _kind(u) == "agent_thought_chunk"]
    messages = [u.update for u in _all() if _kind(u) == "agent_message_chunk"]
    assert [t["content"]["text"] for t in thoughts] == [
        e["part"]["text"] for e in _events() if e["type"] == "reasoning"
    ]
    assert [m["content"]["text"] for m in messages] == [
        e["part"]["text"] for e in _events() if e["type"] == "text"
    ]
    assert thoughts
    assert messages


def test_a_part_seen_again_is_not_repeated():
    mapper = OpenCodeTranscript()

    def text(value: str) -> dict[str, Any]:
        return {"type": "text", "sessionID": "s", "part": {"id": "p", "type": "text", "text": value}}

    assert len(mapper.updates(text("hel"))) == 1
    assert mapper.updates(text("hel")) == []
    (more,) = mapper.updates(text("hello"))
    assert more.update["content"]["text"] == "lo"


def test_step_and_error_events_map_to_nothing():
    mapper = OpenCodeTranscript()
    for event in (
        {"type": "step_start", "sessionID": "s", "part": {}},
        {"type": "step_finish", "sessionID": "s", "part": {"tokens": {}}},
        {"type": "error", "sessionID": "s", "error": {"name": "APIError"}},
    ):
        assert mapper.updates(event) == []
