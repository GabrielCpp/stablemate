"""Cline CLI (``cline --json``) — event vocabulary and adapter."""

from __future__ import annotations

import json
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import usage as _usage
from workhorse.runner.backends import ensure_prompt_is_not_in_argv, prepare_argv_prompt
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id

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


class ClineBackend(JsonlBackend):
    """Cline CLI (``cline --json``), selected with ``--cli cline``."""

    name = "cline"
    default_model = None
    supports_compaction = False

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
    ) -> str:
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
            cmd, node_id, timeout, None, _on_event,
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
