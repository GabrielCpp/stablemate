"""GitHub Copilot CLI (``copilot -p --output-format json``) — event vocabulary and adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from workhorse.config_run import AgentResilience
from workhorse.runner import acp
from workhorse.runner import usage as _usage
from workhorse.runner.backends import (
    AgentProfile,
    ensure_prompt_is_not_in_argv,
    prepare_argv_prompt,
)
from workhorse.runner.backends.delegates import Delegate, warn_unsupported
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import (
    TurnState,
    finalize_turn,
    read_session_id,
    recording,
)


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


class CopilotTranscript(acp.TranscriptMapper):
    """Copilot's ``-p --output-format json`` events as ACP updates.

    The streamed deltas are ignored. The ``assistant.message`` that follows them carries the whole text.
    """

    def __init__(self) -> None:
        super().__init__()
        self._diffs: dict[str, list[dict[str, Any]]] = {}

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
        path = args.get("path")
        diffs = _diffs(tool, args)
        self._diffs[call_id] = diffs
        return acp.tool_call(
            call_id,
            f"{tool} {acp.summarize(args, _SUMMARY_KEYS)}".rstrip(),
            kind,
            content=diffs,
            locations=[{"path": path}] if path and kind in ("read", "edit") else None,
            raw_input=args,
        )

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
    """GitHub Copilot CLI (``copilot -p --output-format json``)."""

    name = "copilot"
    default_model = None
    supports_compaction = False

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return CopilotTranscript()

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        *,
        prompt_path: Path | None = None,
        timeout: float,
        resilience: AgentResilience,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
        agent: AgentProfile | None = None,
        delegates: tuple[Delegate, ...] = (),
    ) -> str:
        warn_unsupported(self.name, delegates)
        sid = read_session_id(session_id_path)
        argv_prompt, attachment = prepare_argv_prompt(prompt, prompt_path)
        cmd = [
            "copilot",
            "-p",
            argv_prompt,
            "--output-format",
            "json",
            "--allow-all",
            "--no-ask-user",
        ]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--effort", effort]
        for d in add_dirs or []:
            cmd += ["--add-dir", d]
        if attachment is not None:
            cmd += ["--attachment", str(attachment)]
        if sid:
            cmd += ["--session-id", sid]
            print(f"[{node_id}] 🔄 Resuming copilot session: {sid[:8]}...", flush=True)
        ensure_prompt_is_not_in_argv(prompt, cmd)
        state = self.stream(
            cmd, node_id, timeout, None, recording(_on_event, session_id_path),
            resilience=resilience, cwd=cwd,
            env_extra=self.harness_env(),
        )
        return finalize_turn("copilot", node_id, state, session_id_path, timeout)

    def compact(
        self,
        session_id_path,
        node_id,
        model=None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ):
        return False
