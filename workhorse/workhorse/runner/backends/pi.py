"""Pi (``pi --mode json``) — event vocabulary, adapter, and the rpc call that compacts a session."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Any

from workhorse.config_run import AgentResilience
from workhorse.runner.backends import TurnRequest
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState
from workhorse.runner.usage import TurnUsage

_SKILL_FOLDERS = (".agents/skills", ".claude/skills")


def _text(message: dict[str, Any]) -> str:
    """The text blocks of one pi message, joined."""
    content = message.get("content")
    if isinstance(content, str):
        return content
    return "".join(
        str(block.get("text") or "")
        for block in content or []
        if isinstance(block, dict) and block.get("type") == "text"
    )


def _usage(message: dict[str, Any]) -> TurnUsage:
    """What one assistant message consumed, from its ``usage`` object."""
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return TurnUsage()
    cost = usage.get("cost")
    return TurnUsage(
        input_tokens=usage.get("input"),
        output_tokens=usage.get("output"),
        cache_read_input_tokens=usage.get("cacheRead"),
        cache_creation_input_tokens=usage.get("cacheWrite"),
        total_cost_usd=cost.get("total") if isinstance(cost, dict) else None,
        steps=1,
    )


def _on_event(event, state: TurnState, node_id):
    """Pi `--mode json`: session → resume id; assistant message_end → answer text (last non-empty wins), usage and a stop-reason error."""
    etype = event.get("type") or ""
    if etype == "session":
        state.session_id = event.get("id") or state.session_id
        return
    if etype != "message_end":
        return
    message = event.get("message") or {}
    if message.get("role") != "assistant":
        return
    state.usage = state.usage.merge(_usage(message))
    text = _text(message).strip()
    if text:
        state.result_text = text
        print(f"[{node_id}] {text[:500]}", flush=True)
    if message.get("stopReason") == "error":
        state.diagnostics.append(
            str(message.get("errorMessage") or "pi stopped on an error")[:500]
        )


def _skill_flags(add_dirs: list[str] | None) -> list[str]:
    """``--skill`` for each skills folder an added directory holds."""
    flags: list[str] = []
    for directory in add_dirs or []:
        for folder in _SKILL_FOLDERS:
            if (Path(directory) / folder).is_dir():
                flags += ["--skill", str(Path(directory) / folder)]
    return flags


class PiBackend(JsonlBackend):
    """Pi (``pi --mode json``), with its rpc mode for a manual compaction."""

    name = "pi"
    default_model = None

    def execute(self, turn: TurnRequest) -> str:
        def command(
            argv_prompt: str, attachment: Path | None, sid: str | None
        ) -> list[str]:
            cmd = ["pi", "--mode", "json"]
            if turn.model:
                cmd += ["--model", turn.model]
            if turn.effort:
                cmd += ["--thinking", turn.effort]
            cmd += ["--session-id", sid or str(uuid.uuid4())]
            cmd += _skill_flags(turn.add_dirs)
            return [*cmd, argv_prompt]

        return self.execute_argv(turn, command, _on_event)

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ) -> bool:
        """Ask pi's rpc mode to compact the node's session, and report whether it answered success."""
        sid = (
            session_id_path.read_text().strip()
            if session_id_path and session_id_path.exists()
            else ""
        )
        if not sid:
            return False
        from workhorse.runner.transcript import store_files

        files = store_files(self.name, sid)
        if not files:
            print(f"[{node_id}] ⚠ compaction call failed", flush=True)
            return False
        cmd = ["pi", "--mode", "rpc", "--session", str(files[-1])]
        if model:
            cmd[3:3] = ["--model", model]
        print(
            f"[{node_id}] 🗜 compacting session {sid[:8]}… to free context", flush=True
        )
        response = _rpc_compact(cmd, timeout, {**self.harness_env()})
        if response is None:
            print(f"[{node_id}] ⚠ compaction call failed", flush=True)
            return False
        if not response.get("success"):
            print(
                f"[{node_id}] ⚠ compaction failed: {response.get('error') or ''}",
                flush=True,
            )
            return False
        return True


def _rpc_compact(
    cmd: list[str], timeout: float, env_extra: dict[str, str]
) -> dict[str, Any] | None:
    """The compact response pi's rpc mode writes, or ``None`` when it never came."""
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            env={**os.environ, **env_extra},
        )
    except OSError:
        return None
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    response: dict[str, Any] | None = None
    try:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(json.dumps({"type": "compact"}) + "\n")
        proc.stdin.flush()
        for raw in proc.stdout:
            try:
                event = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if (
                isinstance(event, dict)
                and event.get("type") == "response"
                and event.get("command") == "compact"
            ):
                response = event
                break
    except OSError:
        response = None
    finally:
        timer.cancel()
        try:
            if proc.stdin is not None:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        if proc.stdout is not None:
            proc.stdout.close()
    return response
