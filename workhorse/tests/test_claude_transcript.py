"""Claude's stream-json mapped to ACP updates, over one recorded turn."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner.backends.claude import ClaudeBackend, ClaudeTranscript

FIXTURE = Path(__file__).parent / "fixtures" / "claude_turn.jsonl"


def _events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _mapped() -> list[tuple[dict[str, Any], list[acp.MappedUpdate]]]:
    mapper = ClaudeTranscript()
    return [(event, mapper.updates(event)) for event in _events()]


def _all() -> list[acp.MappedUpdate]:
    return [update for _event, updates in _mapped() for update in updates]


def _kind(update: acp.MappedUpdate) -> str:
    return update.update["sessionUpdate"]


def _blocks(event: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    content = event.get("message", {}).get("content")
    if not isinstance(content, list):
        return []
    return [block for block in content if block.get("type") == kind]


def test_the_backend_hands_out_a_fresh_claude_mapper_per_turn():
    backend = ClaudeBackend()
    first = backend.transcript_mapper()
    assert isinstance(first, ClaudeTranscript)
    assert backend.transcript_mapper() is not first


def test_the_session_id_comes_from_the_system_event():
    mapper = ClaudeTranscript()
    assert mapper.session_id == ""
    first = _events()[0]
    assert mapper.updates(first) == []
    assert mapper.session_id == first["session_id"]


def test_every_tool_call_has_one_matching_update():
    updates = _all()
    calls = {u.update["toolCallId"] for u in updates if _kind(u) == "tool_call"}
    results = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call_update"]
    assert calls
    assert sorted(results) == sorted(calls)


def test_tool_calls_carry_input_title_and_kind():
    calls = {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call"}
    uses = [
        block
        for event in _events()
        for block in _blocks(event, "tool_use")
        if block["name"] != "TodoWrite"
    ]
    assert uses
    for block in uses:
        call = calls[block["id"]]
        assert call["rawInput"] == block["input"]
        assert call["title"].startswith(block["name"])
        assert call["status"] == "in_progress"
    kinds = {block["name"]: calls[block["id"]]["kind"] for block in uses}
    assert kinds["Read"] == "read"
    assert kinds["Bash"] == "execute"
    assert kinds["Edit"] == "edit"
    assert kinds["Agent"] == "other"


def test_an_edit_carries_a_diff_of_its_old_and_new_text():
    edit = next(
        block
        for event in _events()
        for block in _blocks(event, "tool_use")
        if block["name"] == "Edit"
    )
    call = next(
        u.update for u in _all() if u.update.get("toolCallId") == edit["id"] and _kind(u) == "tool_call"
    )
    assert call["content"] == [
        {
            "type": "diff",
            "path": edit["input"]["file_path"],
            "oldText": edit["input"]["old_string"],
            "newText": edit["input"]["new_string"],
        }
    ]


def test_an_edit_result_keeps_its_diff_since_an_update_replaces_content():
    edit = next(
        block
        for event in _events()
        for block in _blocks(event, "tool_use")
        if block["name"] == "Edit"
    )
    updates = [u.update for u in _all() if u.update.get("toolCallId") == edit["id"]]
    call = next(u for u in updates if u["sessionUpdate"] == "tool_call")
    result = next(u for u in updates if u["sessionUpdate"] == "tool_call_update")
    assert result["content"][: len(call["content"])] == call["content"]


def test_a_todowrite_becomes_a_plan_not_a_tool_call():
    writes = [
        block
        for event in _events()
        for block in _blocks(event, "tool_use")
        if block["name"] == "TodoWrite"
    ]
    plans = [u.update for u in _all() if _kind(u) == "plan"]
    assert len(plans) == len(writes) > 0
    for plan, write in zip(plans, writes, strict=True):
        assert [entry["content"] for entry in plan["entries"]] == [
            todo["content"] for todo in write["input"]["todos"]
        ]
        assert [entry["status"] for entry in plan["entries"]] == [
            todo["status"] for todo in write["input"]["todos"]
        ]
        assert all(entry["priority"] == "medium" for entry in plan["entries"])
    ids = {write["id"] for write in writes}
    assert not any(u.update.get("toolCallId") in ids for u in _all())


def test_a_failed_tool_result_is_marked_failed():
    errors = {
        block["tool_use_id"]
        for event in _events()
        for block in _blocks(event, "tool_result")
        if block.get("is_error")
    }
    assert errors
    updates = {u.update["toolCallId"]: u.update for u in _all() if _kind(u) == "tool_call_update"}
    for tool_id in errors:
        assert updates[tool_id]["status"] == "failed"
    done = [u for tid, u in updates.items() if tid not in errors]
    assert done
    assert all(u["status"] == "completed" for u in done)


def test_a_result_carries_its_text():
    read = next(
        block
        for event in _events()
        for block in _blocks(event, "tool_use")
        if block["name"] == "Read" and event.get("parent_tool_use_id") is None
    )
    result = next(
        block
        for event in _events()
        for block in _blocks(event, "tool_result")
        if block["tool_use_id"] == read["id"]
    )
    update = next(
        u.update for u in _all() if u.update.get("toolCallId") == read["id"] and _kind(u) == "tool_call_update"
    )
    assert update["content"] == [
        {"type": "content", "content": {"type": "text", "text": result["content"]}}
    ]


def test_subagent_events_carry_the_parent_tool_call():
    parented = [
        (event, updates)
        for event, updates in _mapped()
        if event.get("parent_tool_use_id") and updates
    ]
    assert parented
    for event, updates in parented:
        assert all(u.parent == event["parent_tool_use_id"] for u in updates)
    top = [u for event, updates in _mapped() if not event.get("parent_tool_use_id") for u in updates]
    assert top
    assert all(u.parent is None for u in top)


def test_the_final_text_is_an_agent_message():
    messages = [u.update for u in _all() if _kind(u) == "agent_message_chunk"]
    texts = [
        block["text"]
        for event in _events()
        if event.get("type") == "assistant" and not event.get("parent_tool_use_id")
        for block in _blocks(event, "text")
    ]
    assert [m["content"] for m in messages] == [{"type": "text", "text": t} for t in texts]


def test_a_result_event_maps_to_nothing():
    result = next(event for event in _events() if event.get("type") == "result")
    assert ClaudeTranscript().updates(result) == []


def test_write_and_multiedit_tools_map_to_edit_kind():
    mapper = ClaudeTranscript()
    event = {
        "type": "assistant",
        "message": {
            "content": [
                {
                    "type": "tool_use",
                    "id": "t1",
                    "name": "Write",
                    "input": {"file_path": "/work/a.txt", "content": "hi"},
                }
            ]
        },
    }
    (mapped,) = mapper.updates(event)
    assert mapped.update["kind"] == "edit"
    assert mapped.update["content"] == [
        {"type": "diff", "path": "/work/a.txt", "oldText": None, "newText": "hi"}
    ]


TASKS_FIXTURE = Path(__file__).parent / "fixtures" / "claude_tasks_turn.jsonl"
_TASK_TOOLS = ("TaskCreate", "TaskUpdate", "TaskList", "TaskGet")


def _task_events() -> list[dict[str, Any]]:
    return [json.loads(line) for line in TASKS_FIXTURE.read_text().splitlines()]


def _task_updates() -> list[acp.MappedUpdate]:
    mapper = ClaudeTranscript()
    return [update for event in _task_events() for update in mapper.updates(event)]


def _task_uses(*names: str) -> list[dict[str, Any]]:
    return [
        block
        for event in _task_events()
        for block in _blocks(event, "tool_use")
        if block["name"] in names
    ]


def test_task_tools_emit_no_tool_call_and_no_result_update():
    ids = {block["id"] for block in _task_uses(*_TASK_TOOLS)}
    assert ids
    assert not any(u.update.get("toolCallId") in ids for u in _task_updates())


def test_every_other_tool_call_in_a_task_turn_has_one_matching_update():
    updates = _task_updates()
    calls = {u.update["toolCallId"] for u in updates if _kind(u) == "tool_call"}
    results = [u.update["toolCallId"] for u in updates if _kind(u) == "tool_call_update"]
    assert calls
    assert sorted(results) == sorted(calls)


def test_each_task_create_and_update_emits_the_whole_plan():
    plans = [u.update["entries"] for u in _task_updates() if _kind(u) == "plan"]
    changes = _task_uses("TaskCreate", "TaskUpdate")
    assert len(plans) == len(changes)
    assert [e["content"] for e in plans[0]] == ["Read notes.txt"]
    assert [e["content"] for e in plans[2]] == [
        "Read notes.txt",
        "Count lines in notes.txt",
        "Change beta to gamma in notes.txt",
    ]
    assert [e["status"] for e in plans[2]] == ["pending", "pending", "pending"]
    assert [e["status"] for e in plans[3]] == ["in_progress", "pending", "pending"]
    assert [e["status"] for e in plans[-1]] == ["completed", "completed", "completed"]
    assert all(e["priority"] == "medium" for plan in plans for e in plan)


def test_a_task_update_names_its_task_by_the_id_the_create_result_gave():
    mapper = ClaudeTranscript()
    create = {"type": "tool_use", "id": "c1", "name": "TaskCreate", "input": {"subject": "first"}}
    other = {"type": "tool_use", "id": "c2", "name": "TaskCreate", "input": {"subject": "second"}}
    mapper.updates({"type": "assistant", "message": {"content": [create, other]}})
    mapper.updates(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "c2", "content": "Task #7 created successfully: second"},
                    {"type": "tool_result", "tool_use_id": "c1", "content": "Task #6 created successfully: first"},
                ]
            },
        }
    )
    update = {"type": "tool_use", "id": "u1", "name": "TaskUpdate", "input": {"taskId": "7", "status": "completed"}}
    (mapped,) = mapper.updates({"type": "assistant", "message": {"content": [update]}})
    assert [(e["content"], e["status"]) for e in mapped.update["entries"]] == [
        ("first", "pending"),
        ("second", "completed"),
    ]


def test_a_task_update_can_rename_and_delete():
    mapper = ClaudeTranscript()

    def create(call_id: str, number: int, subject: str) -> None:
        use = {"type": "tool_use", "id": call_id, "name": "TaskCreate", "input": {"subject": subject}}
        mapper.updates({"type": "assistant", "message": {"content": [use]}})
        result = {"type": "tool_result", "tool_use_id": call_id, "content": f"Task #{number} created successfully: {subject}"}
        mapper.updates({"type": "user", "message": {"content": [result]}})

    def update(call_id: str, **fields: str) -> acp.MappedUpdate:
        use = {"type": "tool_use", "id": call_id, "name": "TaskUpdate", "input": fields}
        (mapped,) = mapper.updates({"type": "assistant", "message": {"content": [use]}})
        return mapped

    create("c1", 1, "first")
    create("c2", 2, "second")
    renamed = update("u1", taskId="1", subject="renamed")
    assert [e["content"] for e in renamed.update["entries"]] == ["renamed", "second"]
    deleted = update("u2", taskId="2", status="deleted")
    assert [e["content"] for e in deleted.update["entries"]] == ["renamed"]


def test_a_task_update_for_an_unknown_task_emits_nothing():
    mapper = ClaudeTranscript()
    use = {"type": "tool_use", "id": "u1", "name": "TaskUpdate", "input": {"taskId": "9", "status": "completed"}}
    assert mapper.updates({"type": "assistant", "message": {"content": [use]}}) == []
