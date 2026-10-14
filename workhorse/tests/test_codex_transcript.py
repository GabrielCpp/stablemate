"""Codex's ``exec --json`` events mapped to ACP updates, over one recorded turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner.backends.codex import CodexBackend, CodexTranscript

FIXTURE = Path(__file__).parent / "fixtures" / "codex_turn.jsonl"


def _events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _all() -> list[acp.MappedUpdate]:
    mapper = CodexTranscript()
    return [update for event in _events() for update in mapper.updates(event)]


def _kind(update: acp.MappedUpdate) -> str:
    return update.update["sessionUpdate"]


def _items(kind: str, event_type: str = "item.completed") -> list[dict[str, Any]]:
    return [
        event["item"]
        for event in _events()
        if event["type"] == event_type and event["item"]["type"] == kind
    ]


def _calls() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call"}


def _results() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call_update"}


def test_the_backend_hands_out_a_fresh_codex_mapper_per_turn():
    backend = CodexBackend()
    first = backend.transcript_mapper()
    assert isinstance(first, CodexTranscript)
    assert backend.transcript_mapper() is not first


def test_the_session_id_comes_from_thread_started():
    mapper = CodexTranscript()
    first = _events()[0]
    assert mapper.updates(first) == []
    assert mapper.session_id == first["thread_id"]


def test_every_tool_call_has_one_matching_update():
    updates = _all()
    calls = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call"]
    results = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call_update"]
    assert calls
    assert len(set(calls)) == len(calls)
    assert sorted(results) == sorted(calls)


def test_agent_messages_and_reasoning_become_chunks():
    messages = [u.update for u in _all() if _kind(u) == "agent_message_chunk"]
    thoughts = [u.update for u in _all() if _kind(u) == "agent_thought_chunk"]
    assert [m["content"]["text"] for m in messages] == [i["text"] for i in _items("agent_message")]
    assert [t["content"]["text"] for t in thoughts] == [i["text"] for i in _items("reasoning")]
    assert thoughts


def test_a_command_is_an_execute_call_with_its_output():
    commands = _items("command_execution")
    calls, results = _calls(), _results()
    assert commands
    for item in commands:
        call = calls[item["id"]]
        assert call["kind"] == "execute"
        assert call["status"] == "in_progress"
        assert call["title"] == item["command"]
        assert call["rawInput"] == {"command": item["command"]}
        assert results[item["id"]]["content"] == [
            {"type": "content", "content": {"type": "text", "text": item["aggregated_output"]}}
        ]


def test_a_command_that_exits_non_zero_is_failed():
    results = _results()
    failed = [i for i in _items("command_execution") if i["exit_code"]]
    done = [i for i in _items("command_execution") if i["exit_code"] == 0]
    assert failed
    assert done
    assert all(results[i["id"]]["status"] == "failed" for i in failed)
    assert all(results[i["id"]]["status"] == "completed" for i in done)


def test_a_zero_exit_reported_failed_is_still_failed():
    mapper = CodexTranscript()
    item = {"id": "c", "type": "command_execution", "command": "x", "aggregated_output": "", "exit_code": 0}
    assert mapper.updates({"type": "item.started", "item": {**item, "status": "in_progress"}})
    (done,) = mapper.updates({"type": "item.completed", "item": {**item, "status": "failed"}})
    assert done.update["status"] == "failed"


def test_a_file_change_is_an_edit_with_one_location_per_path():
    (change,) = _items("file_change")
    call = _calls()[change["id"]]
    assert call["kind"] == "edit"
    assert call["locations"] == [{"path": c["path"]} for c in change["changes"]]
    assert "content" not in call
    assert _results()[change["id"]]["status"] == "completed"
    assert "content" not in _results()[change["id"]]


def test_a_web_search_is_a_fetch_call_that_ends_with_its_query():
    (search,) = _items("web_search")
    call = _calls()[search["id"]]
    assert call["kind"] == "fetch"
    result = _results()[search["id"]]
    assert result["status"] == "completed"
    assert result["content"] == [
        {"type": "content", "content": {"type": "text", "text": search["query"]}}
    ]


def test_an_mcp_tool_call_is_an_other_call_with_its_arguments_and_result():
    mapper = CodexTranscript()
    item = {
        "id": "m",
        "type": "mcp_tool_call",
        "server": "docs",
        "tool": "lookup",
        "arguments": {"q": "x"},
        "result": None,
        "error": None,
        "status": "in_progress",
    }
    (call,) = mapper.updates({"type": "item.started", "item": item})
    assert call.update["kind"] == "other"
    assert call.update["title"] == "docs.lookup"
    assert call.update["rawInput"] == {"q": "x"}
    finished = {**item, "status": "completed", "result": {"content": [{"type": "text", "text": "found"}]}}
    (done,) = mapper.updates({"type": "item.completed", "item": finished})
    assert done.update["status"] == "completed"
    assert done.update["content"] == [
        {"type": "content", "content": {"type": "text", "text": "found"}}
    ]


def test_a_failed_mcp_tool_call_carries_its_error():
    mapper = CodexTranscript()
    item = {"id": "m", "type": "mcp_tool_call", "server": "docs", "tool": "lookup", "arguments": {}}
    mapper.updates({"type": "item.started", "item": {**item, "status": "in_progress"}})
    failed = {**item, "status": "failed", "error": {"message": "boom"}}
    (done,) = mapper.updates({"type": "item.completed", "item": failed})
    assert done.update["status"] == "failed"
    assert done.update["content"] == [
        {"type": "content", "content": {"type": "text", "text": "boom"}}
    ]


def test_a_todo_list_becomes_a_plan_on_every_change():
    mapper = CodexTranscript()
    items = [{"text": "read", "completed": True}, {"text": "edit", "completed": False}]
    events = [
        {"type": "item.started", "item": {"id": "t", "type": "todo_list", "items": items}},
        {"type": "item.updated", "item": {"id": "t", "type": "todo_list", "items": items}},
        {"type": "item.completed", "item": {"id": "t", "type": "todo_list", "items": items}},
    ]
    for event in events:
        (mapped,) = mapper.updates(event)
        assert mapped.update == {
            "sessionUpdate": "plan",
            "entries": [
                {"content": "read", "priority": "medium", "status": "completed"},
                {"content": "edit", "priority": "medium", "status": "pending"},
            ],
        }


def test_a_result_with_no_start_still_shows_its_call():
    mapper = CodexTranscript()
    item = {"id": "c", "type": "command_execution", "command": "ls", "aggregated_output": "a\n", "exit_code": 0, "status": "completed"}
    (call,) = mapper.updates({"type": "item.completed", "item": item})
    assert call.update["sessionUpdate"] == "tool_call"
    assert call.update["status"] == "completed"
    assert call.update["content"][0]["content"]["text"] == "a\n"


def test_lifecycle_and_error_events_map_to_nothing():
    mapper = CodexTranscript()
    for event in (
        {"type": "turn.started"},
        {"type": "turn.completed", "usage": {}},
        {"type": "turn.failed", "error": {"message": "x"}},
        {"type": "error", "message": "x"},
        {"type": "item.completed", "item": {"id": "e", "type": "error", "message": "x"}},
    ):
        assert mapper.updates(event) == []
