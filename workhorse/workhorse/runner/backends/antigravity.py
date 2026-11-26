from __future__ import annotations

from pathlib import Path
from typing import Any

from workhorse.config_run import AgentResilience
from workhorse.runner import acp
from workhorse.runner.backends import TurnRequest
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState
from workhorse.runner.usage import TurnUsage


def _count(usage: dict[Any, Any], key: str) -> int | None:
    value = usage.get(key)
    return value if isinstance(value, int) and value else None


def _usage(usage: object, steps: int) -> TurnUsage:
    if not isinstance(usage, dict):
        return TurnUsage(steps=steps or None)
    return TurnUsage(
        input_tokens=_count(usage, "input_tokens"),
        output_tokens=_count(usage, "output_tokens"),
        cache_read_input_tokens=_count(usage, "cache_read_tokens"),
        reasoning_output_tokens=_count(usage, "thinking_tokens"),
        steps=steps or None,
    )


class _Steps:
    def __init__(self) -> None:
        self.text: dict[int, str] = {}
        self.finished = 0


def _on_step(
    step: dict[str, Any], steps: _Steps, state: TurnState, node_id: str
) -> None:
    state.session_id = step.get("conversation_id") or state.session_id
    if step.get("step_type") != "agent_response":
        return
    index = int(step.get("step_index") or 0)
    steps.text[index] = steps.text.get(index, "") + str(step.get("text_delta") or "")
    if step.get("state") != "DONE":
        return
    steps.finished += 1
    text = steps.text[index].strip()
    if text:
        state.result_text = text
        print(f"[{node_id}] {text[:500]}", flush=True)


def _on_result(result: dict[str, Any], steps: _Steps, state: TurnState) -> None:
    state.session_id = result.get("conversation_id") or state.session_id
    state.usage = _usage(result.get("usage"), steps.finished)
    if result.get("status") != "SUCCESS":
        state.diagnostics.append(
            str(
                result.get("error")
                or f"agy finished with status {result.get('status')}"
            )[:2000]
        )
        return
    if not state.result_text:
        state.result_text = str(result.get("response") or "").strip()


def event_reader():
    steps = _Steps()

    def on_event(event: dict[str, Any], state: TurnState, node_id: str) -> None:
        kind = event.get("event")
        if kind == "init":
            state.session_id = event.get("conversation_id") or state.session_id
        elif kind == "step_update" and isinstance(event.get("step_update"), dict):
            _on_step(event["step_update"], steps, state, node_id)
        elif kind == "result" and isinstance(event.get("result"), dict):
            _on_result(event["result"], steps, state)

    return on_event


_TOOL_KINDS = {
    "read_file": "read",
    "list_dir": "read",
    "edit_file": "edit",
    "write_file": "edit",
    "run_command": "execute",
    "grep_search": "search",
    "find_by_name": "search",
    "search_web": "fetch",
    "read_url_content": "fetch",
}
_SUMMARY_KEYS = ("Path", "CommandLine", "Query", "Pattern", "Url", "Action")
_FAILED = ("ERROR", "FAILED", "CANCELED", "CANCELLED")


def _diffs(tool: str, args: dict[str, Any]) -> list[dict[str, Any]]:
    path = str(args.get("Path") or "")
    if tool == "edit_file" and "Target" in args and "Replacement" in args:
        return [acp.diff_item(path, str(args["Target"]), str(args["Replacement"]))]
    if tool == "write_file" and "Content" in args:
        return [acp.diff_item(path, None, str(args["Content"]))]
    return []


class AntigravityTranscript(acp.DiffTrackingMapper):
    def __init__(self) -> None:
        super().__init__()
        self._text: dict[int, str] = {}

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        self.session_id = event.get("conversation_id") or self.session_id
        step = event.get("step_update")
        if event.get("event") != "step_update" or not isinstance(step, dict):
            return []
        self.session_id = step.get("conversation_id") or self.session_id
        kind = step.get("step_type")
        if kind == "agent_response":
            return self._response(step)
        if kind in ("tool", "subagent"):
            return self._tool(step)
        return []

    def _response(self, step: dict[str, Any]) -> list[acp.MappedUpdate]:
        index = int(step.get("step_index") or 0)
        self._text[index] = self._text.get(index, "") + str(step.get("text_delta") or "")
        if step.get("state") != "DONE":
            return []
        text = self._text.pop(index).strip()
        return [acp.MappedUpdate(acp.agent_message_chunk(text))] if text else []

    def _tool(self, step: dict[str, Any]) -> list[acp.MappedUpdate]:
        call_id = f"{step.get('conversation_id') or self.session_id}:{step.get('step_index')}"
        updates: list[acp.MappedUpdate] = []
        if call_id not in self._diffs:
            updates.append(acp.MappedUpdate(self._call(call_id, step)))
        state = str(step.get("state") or "")
        if state == "DONE" or state in _FAILED:
            diffs = self._diffs.pop(call_id, [])
            output = str((step.get("tool_info") or {}).get("output") or "")
            content = [*diffs, acp.text_item(output)] if output else diffs
            status = "completed" if state == "DONE" else "failed"
            updates.append(acp.MappedUpdate(acp.tool_call_update(call_id, status=status, content=content or None)))
        return updates

    def _call(self, call_id: str, step: dict[str, Any]) -> acp.Update:
        tool = str(step.get("tool_name") or "tool")
        if step.get("step_type") == "subagent":
            agents = (step.get("subagent_info") or {}).get("subagents") or []
            names = ", ".join(str(agent.get("type_name") or "?") for agent in agents)
            self._diffs[call_id] = []
            return acp.tool_call(call_id, f"{tool} {names}".rstrip(), "other", raw_input=agents)
        args = (step.get("tool_info") or {}).get("parameters") or {}
        kind = _TOOL_KINDS.get(tool, "other")
        return self.open_call(call_id, tool, args, kind, _diffs(tool, args), _SUMMARY_KEYS, args.get("Path"))


def command(turn: TurnRequest, argv_prompt: str, sid: str | None) -> list[str]:
    cmd = [
        "agy",
        "-p",
        argv_prompt,
        "--output-format",
        "stream-json",
        "--dangerously-skip-permissions",
    ]
    if turn.model:
        cmd += ["--model", turn.model]
    if turn.effort:
        cmd += ["--effort", turn.effort]
    if sid:
        cmd += ["--conversation", sid]
    for directory in turn.add_dirs or []:
        cmd += ["--add-dir", directory]
    if turn.agent is not None and turn.agent.confined:
        cmd.append("--sandbox")
    return cmd


class AntigravityBackend(JsonlBackend):
    name = "antigravity"
    default_model = "gemini-4-hydrogen-high"

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return AntigravityTranscript()

    def execute(self, turn: TurnRequest) -> str:
        return self.execute_argv(
            turn,
            lambda argv_prompt, _attachment, sid: command(turn, argv_prompt, sid),
            event_reader(),
        )

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ) -> bool:
        sid = (
            session_id_path.read_text().strip()
            if session_id_path and session_id_path.exists()
            else ""
        )
        if not sid:
            return False
        cmd = [
            "agy",
            "-p",
            "/compact",
            "--output-format",
            "stream-json",
            "--conversation",
            sid,
        ]
        if model:
            cmd += ["--model", model]
        print(
            f"[{node_id}] 🗜 compacting conversation {sid[:8]}… to free context",
            flush=True,
        )
        state = self.stream(
            cmd,
            node_id,
            timeout,
            None,
            event_reader(),
            resilience=resilience,
            env_extra=self.harness_env(),
        )
        if state.timed_out or state.returncode != 0 or state.diagnostics:
            print(
                f"[{node_id}] ⚠ compaction failed: {state.diagnostics_text[:300]}",
                flush=True,
            )
            return False
        return True
