"""GitHub Copilot CLI (``copilot --prompt=<prompt> --output-format json``) — event vocabulary and adapter."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner import usage as _usage
from workhorse.runner.backends import TurnRequest
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, read_session_id


def _on_event(event, state: TurnState, node_id):
    """Copilot `-p --output-format json`: assistant.message.data.content → answer text (last non-empty wins); result → sessionId + exitCode."""
    etype = event.get("type") or ""
    if etype == "assistant.message":
        content = (event.get("data") or {}).get("content") or ""
        if content:
            state.result_text = content
            print(f"[{node_id}] {content.strip()[:500]}", flush=True)
    elif etype == "result":
        if event.get("sessionId"):
            state.session_id = event["sessionId"]
        state.usage = state.usage.merge(_usage.normalize(event))
        exit_code = event.get("exitCode")
        if exit_code not in (0, None):
            state.diagnostics.append(f"copilot exitCode={exit_code}")
    elif "error" in etype:
        state.diagnostics.append(json.dumps(event)[:500])


_NANO_AIU_PER_USD = 1e9 / 0.01


def _count(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _record_usage(record: dict[str, Any]) -> _usage.TurnUsage:
    """One ``session.usage_record`` as canonical usage: the CLI counts cache reads and writes inside ``inputTokens`` and ``reasoningTokens`` inside ``outputTokens``, its ``cost`` is premium requests, not dollars, and ``copilotUsage.totalNanoAiu`` is the AI credits the call billed, in billionths."""
    data = (record.get("data") or {}).get("usage") or {}
    nano_aiu = _count((data.get("copilotUsage") or {}).get("totalNanoAiu"))
    reads = _count(data.get("cacheReadTokens")) or 0
    writes = _count(data.get("cacheWriteTokens")) or 0
    total_in = _count(data.get("inputTokens"))
    return _usage.TurnUsage(
        input_tokens=None if total_in is None else max(total_in - reads - writes, 0),
        output_tokens=_count(data.get("outputTokens")),
        cache_read_input_tokens=_count(data.get("cacheReadTokens")),
        cache_creation_input_tokens=_count(data.get("cacheWriteTokens")),
        reasoning_output_tokens=_count(data.get("reasoningTokens")),
        total_cost_usd=None if nano_aiu is None else nano_aiu / _NANO_AIU_PER_USD,
    )


def _events_file(session_id: str, home: str | None) -> Path:
    root = Path(home) if home else Path.home() / ".copilot"
    return root / "session-state" / session_id / "events.jsonl"


def _event_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def session_usage(path: Path, skip_lines: int = 0) -> _usage.TurnUsage:
    """The usage of every model call the session log recorded after its first ``skip_lines`` lines."""
    total = _usage.TurnUsage()
    for line in _event_lines(path)[skip_lines:]:
        if '"session.usage_record"' not in line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if record.get("type") == "session.usage_record":
            total = total.merge(_record_usage(record))
    return total


def _with_session_usage(
    on_event: Callable[..., None], home: str | None, baseline: int
) -> Callable[..., None]:
    """``on_event``, adding this turn's usage from the session log once the ``result`` event names the session."""

    def handle(event, state: TurnState, node_id):
        on_event(event, state, node_id)
        if event.get("type") == "result" and state.session_id:
            path = _events_file(state.session_id, home)
            state.usage = state.usage.merge(session_usage(path, baseline))

    return handle


_TOOL_KINDS = {
    "view": "read",
    "edit": "edit",
    "create": "edit",
    "bash": "execute",
    "grep": "search",
    "glob": "search",
    "web_fetch": "fetch",
}
_SUMMARY_KEYS = ("path", "command", "pattern", "url", "query", "description")


def _diffs(tool: str, args: dict[str, Any]) -> list[dict[str, Any]]:
    """The file change a Copilot edit tool's arguments spell out."""
    path = str(args.get("path") or "")
    if tool == "edit" and "old_str" in args and "new_str" in args:
        return [acp.diff_item(path, args["old_str"], args["new_str"])]
    if tool == "create" and "file_text" in args:
        return [acp.diff_item(path, None, args["file_text"])]
    return []


class CopilotTranscript(acp.DiffTrackingMapper):
    """Copilot's ``-p --output-format json`` events as ACP updates.

    The streamed deltas are ignored. The ``assistant.message`` that follows them carries the whole text.
    """

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        etype = event.get("type")
        data = event.get("data") or {}
        if etype == "result":
            self.session_id = event.get("sessionId") or self.session_id
            return []
        if etype in ("assistant.message", "assistant.reasoning"):
            text = str(data.get("content") or "")
            if not text.strip():
                return []
            chunk = acp.agent_message_chunk if etype == "assistant.message" else acp.agent_thought_chunk
            return [acp.MappedUpdate(chunk(text))]
        if etype == "tool.execution_start":
            return [acp.MappedUpdate(self._call(data))]
        if etype == "tool.execution_complete":
            result = self._result(data)
            return [acp.MappedUpdate(result)] if result else []
        return []

    def _call(self, data: dict[str, Any]) -> acp.Update:
        tool = str(data.get("toolName", "?"))
        args = data.get("arguments") or {}
        call_id = str(data.get("toolCallId", ""))
        kind = _TOOL_KINDS.get(tool, "other")
        return self.open_call(call_id, tool, args, kind, _diffs(tool, args), _SUMMARY_KEYS, args.get("path"))

    def _result(self, data: dict[str, Any]) -> acp.Update | None:
        call_id = str(data.get("toolCallId", ""))
        diffs = self._diffs.pop(call_id, None)
        if diffs is None:
            return None
        ok = bool(data.get("success"))
        source = data.get("result") if ok else data.get("error")
        text = str((source or {}).get("content" if ok else "message") or "")
        content = [*diffs, acp.text_item(text)] if text else diffs
        return acp.tool_call_update(call_id, status="completed" if ok else "failed", content=content or None)


class CopilotBackend(JsonlBackend):
    """GitHub Copilot CLI (``copilot --prompt=<prompt> --output-format json``)."""

    name = "copilot"
    default_model = None

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return CopilotTranscript()

    def execute(self, turn: TurnRequest) -> str:
        def command(argv_prompt: str, attachment: Path | None, sid: str | None) -> list[str]:
            cmd = [
                "copilot",
                f"--prompt={argv_prompt}",
                "--output-format",
                "json",
                "--allow-all",
                "--no-ask-user",
            ]
            if turn.model:
                cmd += ["--model", turn.model]
            if turn.effort:
                cmd += ["--effort", turn.effort]
            for d in turn.add_dirs or []:
                cmd += ["--add-dir", d]
            if attachment is not None:
                cmd += ["--attachment", str(attachment)]
            if sid:
                cmd += ["--session-id", sid]
            return cmd

        home = self.harness_env().get("COPILOT_HOME") or os.environ.get("COPILOT_HOME")
        sid = read_session_id(turn.session_id_path)
        baseline = len(_event_lines(_events_file(sid, home))) if sid else 0
        return self.execute_argv(turn, command, _with_session_usage(_on_event, home, baseline))
