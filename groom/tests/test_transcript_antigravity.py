import json
from pathlib import Path

from groom import transcript_parse


def _write(path: Path, records: list[dict]) -> Path:
    path.write_text("".join(json.dumps(record) + "\n" for record in records))
    return path


def test_an_antigravity_tee_keeps_each_answer_and_each_tool_with_its_output(tmp_path: Path) -> None:
    def step(index: int, state: str, kind: str, **extra: object) -> dict:
        return {"event": "step_update", "step_update": {"step_index": index, "state": state, "step_type": kind, **extra}}

    run = {"name": "run_command", "parameters": {"CommandLine": "pytest -q"}, "output": "1 failed"}
    path = _write(tmp_path / "t.jsonl", [
        {"event": "init", "conversation_id": "c", "init": {}},
        step(1, "ACTIVE", "agent_response", text_delta="Running "),
        step(1, "DONE", "agent_response", text_delta="the tests."),
        step(2, "ACTIVE", "tool", tool_name="run_command", tool_info=run),
        step(2, "ERROR", "tool", tool_name="run_command", tool_info=run, duration_seconds=1.5),
        {"event": "result", "result": {"status": "SUCCESS"}},
    ])
    entries = transcript_parse.read_files({"transcript.jsonl": path})
    assert entries is not None
    assert [(item["kind"], item.get("role") or item.get("name")) for item in entries] == [
        ("message", "assistant"), ("tool", "run_command"),
    ]
    assert entries[0]["text"] == "Running the tests."
    assert (entries[1]["summary"], entries[1]["result"], entries[1]["failed"]) == ("pytest -q", "1 failed", True)
