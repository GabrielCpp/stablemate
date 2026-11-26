from __future__ import annotations

import json
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import failure
from workhorse.runner.backends import AgentProfile, turn
from workhorse.runner.backends.antigravity import AntigravityBackend, AntigravityTranscript, event_reader
from workhorse.runner.backends.registry import get_backend

RESILIENCE = AgentResilience()
FIXTURE = Path(__file__).parent / "fixtures" / "antigravity_turn.ndjson"
CONVERSATION = "2f6ebf0e-7962-40f3-b476-ad69505872e3"


def _run(
    tmp_path: Path,
    sid: str | None = None,
    agent: AgentProfile | None = None,
    add_dirs: list[str] | None = None,
) -> list[list[str]]:
    commands: list[list[str]] = []

    def _record(cmd: list[str], *_args: object, **_extra: object) -> turn.TurnState:
        commands.append(cmd)
        return turn.TurnState(result_text="OK", session_id="t")

    sid_path = tmp_path / ".sid"
    if sid:
        sid_path.write_text(sid)
    _ = AntigravityBackend(_record).run_turn(
        "P",
        "n",
        sid_path,
        model="gemini-3.8-flash-low",
        timeout=RESILIENCE.result_timeout_s,
        resilience=RESILIENCE,
        agent=agent or AgentProfile(name="free"),
        effort="high",
        add_dirs=add_dirs,
    )
    return commands


def _replay(lines: list[str]) -> turn.TurnState:
    state = turn.TurnState()
    on_event = event_reader()
    for line in lines:
        on_event(json.loads(line), state, "n")
    return state


def test_the_registry_offers_antigravity() -> None:
    assert isinstance(get_backend("antigravity"), AntigravityBackend)


def test_a_turn_runs_agy_in_print_mode_with_stream_json_the_model_and_the_effort(
    tmp_path: Path,
) -> None:
    (cmd,) = _run(tmp_path)
    assert cmd[:3] == ["agy", "-p", "P"]
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert "--dangerously-skip-permissions" in cmd
    assert cmd[cmd.index("--model") + 1] == "gemini-3.8-flash-low"
    assert cmd[cmd.index("--effort") + 1] == "high"
    assert "--conversation" not in cmd
    assert "--sandbox" not in cmd


def test_a_run_that_names_no_model_names_agys_default_so_its_cost_is_known() -> None:
    assert get_backend("antigravity").default_model == "gemini-4-hydrogen-high"


def test_a_resumed_turn_names_its_conversation(tmp_path: Path) -> None:
    (cmd,) = _run(tmp_path, sid="conv-1")
    assert cmd[cmd.index("--conversation") + 1] == "conv-1"


def test_each_extra_dir_is_added_to_the_workspace(tmp_path: Path) -> None:
    (cmd,) = _run(tmp_path, add_dirs=["/a", "/b"])
    assert [cmd[i + 1] for i, part in enumerate(cmd) if part == "--add-dir"] == ["/a", "/b"]


def test_a_confined_turn_runs_in_the_sandbox(tmp_path: Path) -> None:
    (cmd,) = _run(tmp_path, agent=AgentProfile(name="boxed", confined=True))
    assert "--sandbox" in cmd


def test_the_recorded_turn_gives_its_last_answer_its_conversation_and_its_usage() -> None:
    state = _replay(FIXTURE.read_text().splitlines())
    assert state.session_id == CONVERSATION
    assert state.result_text == '{"answer":4}'
    assert state.usage.input_tokens == 20727
    assert state.usage.output_tokens == 54
    assert state.usage.cache_read_input_tokens == 28843
    assert state.usage.steps == 3
    assert state.diagnostics == []


def test_the_conversation_id_is_known_from_the_first_event() -> None:
    state = _replay(FIXTURE.read_text().splitlines()[:1])
    assert state.session_id == CONVERSATION


def test_a_result_in_error_lands_in_the_diagnostics_and_fails_the_turn() -> None:
    error = {
        "event": "result",
        "result": {"conversation_id": "", "status": "ERROR", "response": "", "error": "model x is not recognized"},
    }
    state = _replay([json.dumps(error)])
    assert state.diagnostics == ["model x is not recognized"]
    assert state.result_text == ""


def test_a_quota_error_reads_as_a_usage_cap() -> None:
    error = {
        "event": "result",
        "result": {"status": "ERROR", "error": "429 RESOURCE_EXHAUSTED: quota exceeded for model"},
    }
    state = _replay([json.dumps(error)])
    assert failure.is_cap(state.diagnostics_text)


def test_compaction_sends_compact_on_the_conversation(tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def _record(cmd: list[str], *_args: object, **_extra: object) -> turn.TurnState:
        commands.append(cmd)
        return turn.TurnState(session_id="conv-1")

    sid_path = tmp_path / ".sid"
    sid_path.write_text("conv-1")
    assert AntigravityBackend(_record).compact(sid_path, "n", timeout=60, resilience=RESILIENCE)
    (cmd,) = commands
    assert cmd[:3] == ["agy", "-p", "/compact"]
    assert cmd[cmd.index("--conversation") + 1] == "conv-1"


def test_compaction_without_a_conversation_does_nothing(tmp_path: Path) -> None:
    assert not AntigravityBackend().compact(tmp_path / ".sid", "n", timeout=60, resilience=RESILIENCE)


def _mapped(lines: list[str]) -> list[dict]:
    mapper = AntigravityTranscript()
    return [each.update for line in lines for each in mapper.updates(json.loads(line))]


def _step(index: int, state: str, tool: str, parameters: dict, output: str = "") -> str:
    info: dict = {"name": tool, "parameters": parameters}
    if output:
        info["output"] = output
    step = {"conversation_id": "c", "step_index": index, "state": state, "step_type": "tool", "tool_name": tool, "tool_info": info}
    return json.dumps({"event": "step_update", "step_update": step})


def test_the_recorded_turn_maps_to_its_command_and_its_answers() -> None:
    updates = _mapped(FIXTURE.read_text().splitlines())
    call, done = (u for u in updates if u["sessionUpdate"].startswith("tool_call"))
    assert (call["title"], call["kind"]) == ("run_command echo hi", "execute")
    assert done["toolCallId"] == call["toolCallId"]
    assert done["status"] == "completed"
    texts = [u["content"]["text"] for u in updates if u["sessionUpdate"] == "agent_message_chunk"]
    assert texts[-2:] == ['{"answer": 4}', '{"answer":4}']


def test_an_edit_carries_its_diff_and_a_failed_call_reads_as_failed() -> None:
    edit = {"Path": "/w/a.py", "Target": "x = 1", "Replacement": "x = 2"}
    updates = _mapped([_step(2, "ACTIVE", "edit_file", edit), _step(2, "ERROR", "edit_file", edit, "no match")])
    call, done = updates
    assert call["content"] == [{"type": "diff", "path": "/w/a.py", "oldText": "x = 1", "newText": "x = 2"}]
    assert call["locations"] == [{"path": "/w/a.py"}]
    assert done["status"] == "failed"
    assert done["content"][-1]["content"]["text"] == "no match"


def test_a_call_seen_only_when_done_still_opens_before_it_closes() -> None:
    updates = _mapped([_step(3, "DONE", "read_file", {"Path": "/w/b"}, "2 lines")])
    assert [u["sessionUpdate"] for u in updates] == ["tool_call", "tool_call_update"]
