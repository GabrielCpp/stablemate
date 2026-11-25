"""OpenCode CLI (``opencode run --format json``) — event vocabulary, adapter, and the out-of-band probe for the ChatGPT/Codex provider's usage-window reset."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner import failure as _failure
from workhorse.runner import usage as _usage
from workhorse.runner.backends import (
    TurnRequest,
    ensure_prompt_is_not_in_argv,
    prepare_argv_prompt,
)
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.opencode_config import (
    OPENCODE_CONFIG_ENV,
    OPENCODE_OUTPUT_TOKEN_MAX,
    OPENCODE_OUTPUT_TOKEN_MAX_ENV,
    OPENCODE_VARIANT,
    config_content,
)
from workhorse.runner.backends.turn import (
    TurnState,
    finalize_turn,
    read_session_id,
    recording,
)
from workhorse.runner.usage import TurnUsage


@dataclass(slots=True)
class _OpenCodeEvents:
    """OpenCode's per-turn event reader, and the text parts it has to remember."""

    parts: dict[str | int, str] = field(default_factory=dict)

    def on_event(self, event, state: TurnState, node_id) -> None:
        """OpenCode `run --format json`: NDJSON events with a top-level ``type`` and ``sessionID``."""
        sid = event.get("sessionID")
        if sid:
            state.session_id = sid
        etype = event.get("type") or ""
        if etype == "step_finish":
            state.usage = state.usage.merge(_usage.normalize(event)).merge(
                TurnUsage(steps=1)
            )
        elif etype == "text":
            part = event.get("part") or {}
            text = part.get("text") or ""
            if text:
                self.parts[part.get("id") or len(self.parts)] = text
                state.result_text = "\n".join(self.parts.values())
                print(f"[{node_id}] {text.strip()[:500]}", flush=True)
        elif etype == "error":
            err = event.get("error") or {}
            data = err.get("data") or {}
            msg = data.get("message") or err.get("name") or json.dumps(event)[:300]
            state.diagnostics.append(str(msg)[:500])


_TOOL_KINDS = {
    "read": "read",
    "edit": "edit",
    "write": "edit",
    "patch": "edit",
    "apply_patch": "edit",
    "bash": "execute",
    "grep": "search",
    "glob": "search",
    "list": "search",
    "webfetch": "fetch",
    "websearch": "fetch",
}
_SUMMARY_KEYS = ("filePath", "path", "command", "pattern", "url", "query", "description")
_PRIORITIES = ("high", "medium", "low")


def _diffs(tool: str, inp: dict[str, Any]) -> list[dict[str, Any]]:
    """The file change an OpenCode edit tool's input spells out."""
    path = str(inp.get("filePath") or "")
    if tool == "edit" and "oldString" in inp and "newString" in inp:
        return [acp.diff_item(path, inp["oldString"], inp["newString"])]
    if tool == "write" and "content" in inp:
        return [acp.diff_item(path, None, inp["content"])]
    return []


class OpenCodeTranscript(acp.TranscriptMapper):
    """OpenCode's ``run --format json`` events as ACP updates.

    A ``tool_use`` event arrives once its tool has finished, so it yields the call and its result together.
    """

    def __init__(self) -> None:
        super().__init__()
        self._seen: dict[str, str] = {}

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        self.session_id = event.get("sessionID") or self.session_id
        part = event.get("part") or {}
        etype = event.get("type")
        if etype in ("text", "reasoning"):
            return [acp.MappedUpdate(u) for u in self._words(etype, part)]
        if etype == "tool_use":
            return [acp.MappedUpdate(u) for u in self._tool(part)]
        return []

    def _words(self, etype: str, part: dict[str, Any]) -> list[acp.Update]:
        text = str(part.get("text") or "")
        key = str(part.get("id") or "")
        before = self._seen.get(key, "") if key else ""
        if key:
            self._seen[key] = text
        fresh = text[len(before):] if text.startswith(before) else text
        if not fresh.strip():
            return []
        chunk = acp.agent_message_chunk if etype == "text" else acp.agent_thought_chunk
        return [chunk(fresh)]

    def _tool(self, part: dict[str, Any]) -> list[acp.Update]:
        tool = str(part.get("tool", "?"))
        state = part.get("state") or {}
        inp = state.get("input") or {}
        if tool == "todowrite":
            return [
                acp.plan(
                    [
                        acp.plan_entry(
                            str(todo.get("content", "")),
                            todo["status"] if todo.get("status") in ("in_progress", "completed") else "pending",
                            todo["priority"] if todo.get("priority") in _PRIORITIES else "medium",
                        )
                        for todo in inp.get("todos") or []
                    ]
                )
            ]
        call_id = str(part.get("callID", ""))
        kind = _TOOL_KINDS.get(tool, "other")
        path = inp.get("filePath")
        diffs = _diffs(tool, inp)
        call = acp.tool_call(
            call_id,
            f"{tool} {acp.summarize(inp, _SUMMARY_KEYS)}".rstrip(),
            kind,
            content=diffs,
            locations=[{"path": path}] if path and kind in ("read", "edit") else None,
            raw_input=inp,
        )
        status = state.get("status")
        if status not in ("completed", "error"):
            return [call]
        failed = status == "error" or state.get("metadata", {}).get("exit") not in (None, 0)
        text = str(state.get("error") if status == "error" else state.get("output") or "")
        content = [*diffs, acp.text_item(text)] if text else diffs
        return [call, acp.tool_call_update(call_id, status="failed" if failed else "completed", content=content or None)]


_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_OPENCODE_AUTH_PATH = Path(
    os.environ.get(
        "OPENCODE_AUTH_PATH", str(Path.home() / ".local/share/opencode/auth.json")
    )
)


def _codex_reset_at(model: str | None, timeout: float = 15.0) -> float | None:
    """Best-effort unix epoch when the ChatGPT/Codex usage window for ``model`` resets."""
    if os.environ.get("WORKHORSE_CODEX_RESET_PROBE", "1").lower() in (
        "0",
        "false",
        "no",
        "",
    ):
        return None
    if not model or not model.lower().startswith("openai/"):
        return None
    try:
        creds = json.loads(_OPENCODE_AUTH_PATH.read_text()).get("openai") or {}
        token, account = creds.get("access"), creds.get("accountId")
        if creds.get("type") != "oauth" or not token:
            return None
        body = json.dumps(
            {
                "model": model.split("/", 1)[1],
                "instructions": "",
                "input": [
                    {
                        "role": "user",
                        "content": [{"type": "input_text", "text": "ping"}],
                    }
                ],
                "stream": True,
                "store": False,
            }
        ).encode()
        req = urllib.request.Request(
            _CODEX_RESPONSES_URL,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "ChatGPT-Account-Id": account or "",
                "Content-Type": "application/json",
                "originator": "opencode",
                "User-Agent": "opencode",
                "OpenAI-Beta": "responses=experimental",
            },
        )
        try:
            resp = urllib.request.urlopen(req, timeout=timeout)
            headers = resp.headers
            resp.close()
        except urllib.error.HTTPError as exc:
            headers = exc.headers
        raw = headers.get("x-codex-primary-reset-at")
        return float(raw) if raw else None
    except Exception:
        return None


class OpenCodeBackend(JsonlBackend):
    """OpenCode CLI (``opencode run --format json``)."""

    name = "opencode"
    default_model = (
        None
    )

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return OpenCodeTranscript()

    def execute(self, turn: TurnRequest) -> str:
        sid = read_session_id(turn.session_id_path)
        argv_prompt, attachment = prepare_argv_prompt(turn.prompt, turn.prompt_path)
        cmd = [
            "opencode",
            "--print-logs",
            "--log-level",
            "ERROR",
            "run",
            "--format",
            "json",
            "--thinking",
            "--auto",
        ]
        if turn.model:
            cmd += ["-m", turn.model]
        variant = OPENCODE_VARIANT.get(turn.effort, turn.effort) if turn.effort else ""
        if variant:
            cmd += ["--variant", variant]
        if sid:
            cmd += ["--session", sid]
            print(f"[{turn.node_id}] 🔄 Resuming opencode session: {sid[:8]}...", flush=True)
        if turn.agent is not None:
            cmd += ["--agent", turn.agent.name]
        if attachment is not None:
            cmd += ["--file", str(attachment)]
        cmd += ["--", argv_prompt]
        ensure_prompt_is_not_in_argv(turn.prompt, cmd)
        env_extra = self.harness_env()
        config = config_content(
            env_extra.get(OPENCODE_CONFIG_ENV), turn.model, turn.agent, turn.cwd, turn.add_dirs, turn.delegates
        )
        if config is not None:
            env_extra = {**env_extra, OPENCODE_CONFIG_ENV: config}
        if OPENCODE_OUTPUT_TOKEN_MAX_ENV not in env_extra:
            env_extra = {
                OPENCODE_OUTPUT_TOKEN_MAX_ENV: OPENCODE_OUTPUT_TOKEN_MAX,
                **env_extra,
            }
        state = self.stream(
            cmd, turn.node_id, turn.timeout, None,
            recording(_OpenCodeEvents().on_event, turn.session_id_path),
            resilience=turn.resilience, cwd=turn.cwd,
            env_extra=env_extra,
        )
        rate_reset_at = (
            _codex_reset_at(turn.model) if _failure.is_cap(state.diagnostics_text) else None
        )
        return finalize_turn(
            "opencode",
            turn.node_id,
            state,
            turn.session_id_path,
            turn.timeout,
            rate_reset_at=rate_reset_at,
        )
