"""Cline's ``--json`` events mapped to ACP updates, over one recorded turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner.backends.cline import ClineBackend, ClineTranscript

FIXTURE = Path(__file__).parent / "fixtures" / "cline_turn.jsonl"


def _events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _all() -> list[acp.MappedUpdate]:
    mapper = ClineTranscript()
    return [update for event in _events() for update in mapper.updates(event)]


def _kind(update: acp.MappedUpdate) -> str:
    return update.update["sessionUpdate"]


def _tool_events(phase: str, name: str | None = None) -> list[dict[str, Any]]:
    return [
        e["event"]
        for e in _events()
        if e["type"] == "agent_event"
        and e["event"]["type"] == phase
        and e["event"].get("contentType") == "tool"
        and (name is None or e["event"]["toolName"] == name)
    ]


def _calls() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call"}


def _results() -> dict[str, dict[str, Any]]:
    return {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call_update"}


def _end(name: str, success: bool) -> dict[str, Any]:
    def ok(output: Any) -> bool:
        items = output if isinstance(output, list) else [output]
        return all(item.get("success", True) for item in items)

    return next(e for e in _tool_events("content_end", name) if ok(e["output"]) is success)


def test_the_backend_hands_out_a_fresh_cline_mapper_per_turn():
    backend = ClineBackend()
    first = backend.transcript_mapper()
    assert isinstance(first, ClineTranscript)
    assert backend.transcript_mapper() is not first


def test_the_session_id_comes_from_the_hook_event_task_id():
    mapper = ClineTranscript()
    first = _events()[0]
    assert mapper.updates(first) == []
    assert mapper.session_id == first["taskId"]


def test_every_tool_call_has_one_matching_update():
    updates = _all()
    calls = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call"]
    results = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call_update"]
    assert calls
    assert len(set(calls)) == len(calls)
    assert sorted(results) == sorted(calls)


def test_tool_calls_carry_input_title_and_kind():
    calls = _calls()
    for name, kind in (
        ("read_files", "read"),
        ("run_commands", "execute"),
        ("apply_patch", "edit"),
        ("team_task", "other"),
    ):
        starts = _tool_events("content_start", name)
        assert starts
        for start in starts:
            call = calls[start["toolCallId"]]
            assert call["kind"] == kind
            assert call["status"] == "in_progress"
            assert call["rawInput"] == start["input"]
            assert call["title"].startswith(name)


def test_a_read_and_a_command_title_say_what_they_touch():
    calls = _calls()
    read = _tool_events("content_start", "read_files")[0]
    assert calls[read["toolCallId"]]["title"] == f"read_files {read['input']['files'][0]['path']}"
    assert calls[read["toolCallId"]]["locations"] == [{"path": read["input"]["files"][0]["path"]}]
    command = _tool_events("content_start", "run_commands")[0]
    assert calls[command["toolCallId"]]["title"] == f"run_commands {command['input']['commands'][0]}"


def test_a_patch_is_an_edit_with_a_diff_on_the_call_and_again_on_the_result():
    start = _tool_events("content_start", "apply_patch")[0]
    path = start["input"]["input"].splitlines()[1].removeprefix("*** Update File: ")
    diff = {"type": "diff", "path": path, "oldText": "alpha\nbeta", "newText": "alpha\ngamma"}
    call = _calls()[start["toolCallId"]]
    assert call["content"] == [diff]
    assert call["locations"] == [{"path": path}]
    result = _results()[start["toolCallId"]]
    assert result["status"] == "completed"
    assert result["content"] == [diff, acp.text_item(_end("apply_patch", True)["output"]["result"])]


def test_a_patch_adding_a_file_is_a_new_file_diff():
    mapper = ClineTranscript()
    patch = "*** Begin Patch\n*** Add File: /work/a.txt\n+hi\n+there\n*** End Patch"
    start = {
        "type": "agent_event",
        "event": {"type": "content_start", "contentType": "tool", "toolCallId": "p", "toolName": "apply_patch", "input": {"input": patch}},
    }
    (call,) = mapper.updates(start)
    assert call.update["content"] == [{"type": "diff", "path": "/work/a.txt", "oldText": None, "newText": "hi\nthere"}]


def test_a_read_result_carries_each_files_text():
    start = _tool_events("content_start", "read_files")[0]
    end = next(e for e in _tool_events("content_end", "read_files") if e["toolCallId"] == start["toolCallId"])
    result = _results()[start["toolCallId"]]
    assert result["status"] == "completed"
    assert result["content"] == [acp.text_item(item["result"]) for item in end["output"]]


def test_a_command_that_fails_is_failed_with_its_output():
    end = _end("run_commands", False)
    result = _results()[end["toolCallId"]]
    assert result["status"] == "failed"
    assert result["content"] == [acp.text_item(end["output"][0]["result"])]


def test_a_read_that_errors_is_failed_and_shows_its_error():
    end = _end("read_files", False)
    result = _results()[end["toolCallId"]]
    assert result["status"] == "failed"
    assert result["content"] == [acp.text_item(end["output"][0]["error"])]


def test_a_successful_command_is_completed():
    end = _end("run_commands", True)
    assert _results()[end["toolCallId"]]["status"] == "completed"


def test_a_tool_that_answers_with_a_bare_object_shows_it_as_json():
    end = _tool_events("content_end", "team_task")[0]
    result = _results()[end["toolCallId"]]
    assert result["status"] == "completed"
    assert result["content"] == [acp.text_item(json.dumps(end["output"]))]


def test_a_denied_tool_is_failed_with_the_denial():
    mapper = ClineTranscript()
    base = {"type": "agent_event"}
    start = {"type": "content_start", "contentType": "tool", "toolCallId": "d", "toolName": "read_files", "input": {"files": []}}
    end = {
        "type": "content_end",
        "contentType": "tool",
        "toolCallId": "d",
        "toolName": "read_files",
        "output": {"error": "needs approval"},
        "error": "{}",
    }
    mapper.updates({**base, "event": start})
    (done,) = mapper.updates({**base, "event": end})
    assert done.update["status"] == "failed"
    assert done.update["content"] == [acp.text_item("needs approval")]


def test_text_and_reasoning_become_chunks_from_their_ends_only():
    messages = [u.update["content"]["text"] for u in _all() if _kind(u) == "agent_message_chunk"]
    thoughts = [u.update["content"]["text"] for u in _all() if _kind(u) == "agent_thought_chunk"]
    ends = [e["event"] for e in _events() if e["type"] == "agent_event" and e["event"]["type"] == "content_end"]
    assert messages == [e["text"] for e in ends if e["contentType"] == "text"]
    assert thoughts == [e["reasoning"] for e in ends if e["contentType"] == "reasoning"]
    assert messages
    assert thoughts


def test_updates_for_unknown_calls_and_other_events_map_to_nothing():
    mapper = ClineTranscript()
    stray = {
        "type": "agent_event",
        "event": {"type": "content_end", "contentType": "tool", "toolCallId": "x", "toolName": "read_files", "output": []},
    }
    assert mapper.updates(stray) == []
    for event in (
        {"type": "run_result", "finishReason": "completed", "text": "done"},
        {"type": "agent_event", "event": {"type": "usage"}},
        {"type": "agent_event", "event": {"type": "iteration_start", "iteration": 1}},
        {"type": "error", "message": "x"},
    ):
        assert mapper.updates(event) == []
