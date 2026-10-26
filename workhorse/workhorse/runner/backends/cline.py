"""Cline CLI (``cline --json``) — event vocabulary and adapter."""

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
    warn_unenforced_confinement,
)
from workhorse.runner.backends.delegates import Delegate, warn_unsupported
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import (
    TurnState,
    finalize_turn,
    read_session_id,
    recording,
)

_EFFORTS = frozenset({"none", "low", "medium", "high", "xhigh"})


def _on_event(event, state: TurnState, node_id) -> None:
    """cline ``--json``: NDJSON, every line a ``{"type":…,"ts":…}`` envelope."""
    etype = event.get("type") or ""
    if etype == "hook_event":
        if event.get("taskId"):
            state.session_id = event["taskId"]
        return
    if etype == "run_result":
        state.result_text = (event.get("text") or "").strip()
        state.usage = state.usage.merge(_usage.normalize(event))
        reason = event.get("finishReason") or ""
        if reason and reason != "completed":
            state.diagnostics.append(f"cline finishReason={reason}")
        return
    if etype == "agent_event":
        inner = event.get("event") or {}
        if inner.get("type") == "content_end" and inner.get("contentType") == "text":
            text = (inner.get("text") or "").strip()
            if text:
                print(f"[{node_id}] {text[:500]}", flush=True)
        return
    if "error" in etype:
        state.diagnostics.append(json.dumps(event)[:500])


_TOOL_KINDS = {
    "read_files": "read",
    "run_commands": "execute",
    "apply_patch": "edit",
    "editor": "edit",
    "search_codebase": "search",
    "fetch_web_content": "fetch",
}
_SUMMARY_KEYS = ("path", "command", "query", "url", "title", "action")
_PATCH_FILE = "*** "


def _patch_files(patch: str) -> list[tuple[str, str, list[str]]]:
    """The ``(verb, path, body lines)`` of each file section in an ``apply_patch`` input."""
    files: list[tuple[str, str, list[str]]] = []
    for line in patch.splitlines():
        head, _, path = line.partition(" File: ")
        if head in ("*** Add", "*** Update", "*** Delete"):
            files.append((head.removeprefix(_PATCH_FILE), path, []))
        elif files and not line.startswith(_PATCH_FILE) and not line.startswith("@@"):
            files[-1][2].append(line)
    return files


def _diffs(tool: str, inp: dict[str, Any]) -> list[dict[str, Any]]:
    """The file changes a Cline ``apply_patch`` input spells out."""
    if tool != "apply_patch":
        return []
    diffs = []
    for verb, path, body in _patch_files(str(inp.get("input") or "")):
        if verb == "Add":
            diffs.append(acp.diff_item(path, None, "\n".join(line[1:] for line in body if line.startswith("+"))))
        elif verb == "Update":
            old = "\n".join(line[1:] for line in body if line[:1] in ("-", " "))
            new = "\n".join(line[1:] for line in body if line[:1] in ("+", " "))
            diffs.append(acp.diff_item(path, old, new))
    return diffs


def _targets(tool: str, inp: dict[str, Any]) -> dict[str, Any]:
    """``inp`` with the paths or commands a Cline tool names under the keys a call title reads."""
    if tool == "read_files":
        return {"path": ", ".join(str(f.get("path", "")) for f in inp.get("files") or [])}
    if tool == "run_commands":
        return {"command": "; ".join(str(c) for c in inp.get("commands") or [])}
    if tool == "apply_patch":
        return {"path": ", ".join(path for _verb, path, _body in _patch_files(str(inp.get("input") or "")))}
    return inp


class ClineTranscript(acp.TranscriptMapper):
    """Cline's ``--json`` events as ACP updates.

    A tool's streamed ``content_update`` events are ignored. Its ``content_end`` carries the whole result.
    """

    def __init__(self) -> None:
        super().__init__()
        self._diffs: dict[str, list[dict[str, Any]]] = {}

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        etype = event.get("type")
        if etype == "hook_event":
            self.session_id = event.get("taskId") or self.session_id
            return []
        inner = event.get("event") or {}
        if etype != "agent_event" or inner.get("type") not in ("content_start", "content_end"):
            return []
        phase, kind = inner["type"], inner.get("contentType")
        if kind == "tool":
            update = self._call(inner) if phase == "content_start" else self._result(inner)
            return [acp.MappedUpdate(update)] if update else []
        if phase == "content_end" and kind in ("text", "reasoning"):
            text = str(inner.get(kind) or "")
            if text.strip():
                chunk = acp.agent_message_chunk if kind == "text" else acp.agent_thought_chunk
                return [acp.MappedUpdate(chunk(text))]
        return []

    def _call(self, inner: dict[str, Any]) -> acp.Update:
        tool = str(inner.get("toolName", "?"))
        inp = inner.get("input") or {}
        call_id = str(inner.get("toolCallId", ""))
        kind = _TOOL_KINDS.get(tool, "other")
        targets = _targets(tool, inp)
        diffs = _diffs(tool, inp)
        self._diffs[call_id] = diffs
        locations = [{"path": path} for path in str(targets.get("path") or "").split(", ") if path]
        return acp.tool_call(
            call_id,
            f"{tool} {acp.summarize(targets, _SUMMARY_KEYS)}".rstrip(),
            kind,
            content=diffs,
            locations=locations if kind in ("read", "edit") else None,
            raw_input=inp,
        )

    def _result(self, inner: dict[str, Any]) -> acp.Update | None:
        call_id = str(inner.get("toolCallId", ""))
        diffs = self._diffs.pop(call_id, None)
        if diffs is None:
            return None
        output = inner.get("output")
        items = output if isinstance(output, list) else [output or {}]
        failed = bool(inner.get("error")) or any(
            isinstance(item, dict) and (item.get("success") is False or (item.get("error") and "success" not in item))
            for item in items
        )
        texts = [self._text(item) for item in items]
        content = [*diffs, *(acp.text_item(text) for text in texts if text)]
        return acp.tool_call_update(call_id, status="failed" if failed else "completed", content=content or None)

    @staticmethod
    def _text(item: Any) -> str:
        if not isinstance(item, dict):
            return str(item)
        text = item.get("result") or item.get("error")
        if isinstance(text, str):
            return text
        return json.dumps(item) if item else ""


class ClineBackend(JsonlBackend):
    """Cline CLI (``cline --json``), selected with ``--cli cline``."""

    name = "cline"
    default_model = None
    supports_compaction = False
    supports_subagents = False

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return ClineTranscript()

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
        warn_unenforced_confinement(self.name, node_id, agent)
        sid = read_session_id(session_id_path)
        argv_prompt, _attachment = prepare_argv_prompt(prompt, prompt_path)
        cmd = [
            "cline",
            "--json",
            "--auto-approve",
            "true",
            "--compaction",
            "basic",
        ]
        if model:
            cmd += ["--model", model]
        if effort in _EFFORTS:
            cmd += ["--thinking", effort]
        if cwd:
            cmd += ["--cwd", cwd]
        if sid:
            cmd += ["--id", sid]
            print(f"[{node_id}] 🔄 Resuming cline session: {sid[:8]}...", flush=True)
        cmd += ["--", argv_prompt]
        ensure_prompt_is_not_in_argv(prompt, cmd)
        state = self.stream(
            cmd, node_id, timeout, None, recording(_on_event, session_id_path),
            resilience=resilience, cwd=cwd,
            env_extra=self.harness_env(),
        )
        return finalize_turn("cline", node_id, state, session_id_path, timeout)

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
