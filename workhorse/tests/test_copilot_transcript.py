"""Copilot's ``-p --output-format json`` events mapped to ACP updates, over one recorded turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner.backends.copilot import CopilotBackend, CopilotTranscript

FIXTURE = Path(__file__).parent / "fixtures" / "copilot_turn.jsonl"


def _events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _all() -> list[acp.MappedUpdate]:
    mapper = CopilotTranscript()
    return [update for event in _events() for update in mapper.updates(event)]


def _kind(update: acp.MappedUpdate) -> str:
    return update.update["sessionUpdate"]


def _starts(name: str) -> list[dict[str, Any]]:
    return [e["data"] for e in _events() if e["type"] == "tool.execution_start" and e["data"]["toolName"] == name]


def _completes() -> dict[str, dict[str, Any]]:
    return {e["data"]["toolCallId"]: e["data"] for e in _events() if e["type"] == "tool.execution_complete"}


def _calls() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call"}


def _results() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call_update"}


def test_the_backend_hands_out_a_fresh_copilot_mapper_per_turn():
    backend = CopilotBackend()
    first = backend.transcript_mapper()
    assert isinstance(first, CopilotTranscript)
    assert backend.transcript_mapper() is not first


def test_the_session_id_comes_from_the_result_event():
    mapper = CopilotTranscript()
    result = _events()[-1]
    assert mapper.updates(result) == []
    assert mapper.session_id == result["sessionId"]


def test_every_tool_call_has_one_matching_update():
    updates = _all()
    calls = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call"]
    results = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call_update"]
    assert calls
    assert len(set(calls)) == len(calls)
    assert sorted(results) == sorted(calls)


def test_tool_calls_carry_input_title_and_kind():
    calls = _calls()
    for name, kind in (("view", "read"), ("bash", "execute"), ("edit", "edit"), ("sql", "other")):
        starts = _starts(name)
        assert starts
        for start in starts:
            call = calls[start["toolCallId"]]
            assert call["kind"] == kind
            assert call["status"] == "in_progress"
            assert call["rawInput"] == start["arguments"]
            assert call["title"].startswith(name)


def test_a_view_or_edit_names_its_file_as_a_location():
    calls = _calls()
    for start in (*_starts("view"), *_starts("edit")):
        assert calls[start["toolCallId"]]["locations"] == [{"path": start["arguments"]["path"]}]


def test_an_edit_carries_its_diff_on_the_call_and_again_on_a_successful_result():
    done = next(s for s in _starts("edit") if _completes()[s["toolCallId"]]["success"])
    args = done["arguments"]
    diff = {"type": "diff", "path": args["path"], "oldText": args["old_str"], "newText": args["new_str"]}
    assert _calls()[done["toolCallId"]]["content"] == [diff]
    result = _results()[done["toolCallId"]]
    assert result["status"] == "completed"
    assert result["content"] == [diff, acp.text_item(_completes()[done["toolCallId"]]["result"]["content"])]


def test_a_failed_edit_shows_its_error_after_the_diff():
    failed = next(s for s in _starts("edit") if not _completes()[s["toolCallId"]]["success"])
    result = _results()[failed["toolCallId"]]
    assert result["status"] == "failed"
    assert result["content"][-1] == acp.text_item(_completes()[failed["toolCallId"]]["error"]["message"])
    assert result["content"][0]["type"] == "diff"


def test_a_denied_command_is_failed_with_its_reason():
    denied = [s for s in _starts("bash") if not _completes()[s["toolCallId"]]["success"]]
    assert denied
    for start in denied:
        result = _results()[start["toolCallId"]]
        assert result["status"] == "failed"
        assert result["content"] == [acp.text_item(_completes()[start["toolCallId"]]["error"]["message"])]


def test_a_result_carries_the_tool_output():
    start = _starts("view")[0]
    result = _results()[start["toolCallId"]]
    assert result["status"] == "completed"
    assert result["content"] == [acp.text_item(_completes()[start["toolCallId"]]["result"]["content"])]


def test_a_create_is_a_new_file_diff():
    mapper = CopilotTranscript()
    start = {
        "type": "tool.execution_start",
        "data": {"toolCallId": "c", "toolName": "create", "arguments": {"path": "/work/a", "file_text": "hi"}},
    }
    (call,) = mapper.updates(start)
    assert call.update["kind"] == "edit"
    assert call.update["content"] == [{"type": "diff", "path": "/work/a", "oldText": None, "newText": "hi"}]


def test_assistant_text_becomes_a_message_and_empty_text_is_skipped():
    messages = [u.update["content"]["text"] for u in _all() if _kind(u) == "agent_message_chunk"]
    texts = [e["data"]["content"] for e in _events() if e["type"] == "assistant.message" and e["data"]["content"]]
    assert messages == texts
    assert messages


def test_reasoning_text_becomes_a_thought():
    mapper = CopilotTranscript()
    (thought,) = mapper.updates({"type": "assistant.reasoning", "data": {"content": "hmm"}})
    assert thought.update["sessionUpdate"] == "agent_thought_chunk"
    assert thought.update["content"]["text"] == "hmm"


def test_a_result_with_no_start_maps_to_nothing():
    mapper = CopilotTranscript()
    event = {"type": "tool.execution_complete", "data": {"toolCallId": "x", "success": True, "result": {"content": "a"}}}
    assert mapper.updates(event) == []


def test_user_echo_and_streaming_events_map_to_nothing():
    mapper = CopilotTranscript()
    for event in (
        {"type": "user.message", "data": {"content": "go"}},
        {"type": "assistant.message_delta", "data": {"deltaContent": "x"}},
        {"type": "assistant.turn_start", "data": {}},
        {"type": "session.warning", "data": {}},
    ):
        assert mapper.updates(event) == []
