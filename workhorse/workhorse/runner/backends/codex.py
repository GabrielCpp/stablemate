"""OpenAI Codex CLI (``codex exec --json``) — its event vocabulary and its adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import usage as _usage
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id


def _parse_codex_model(model: str | None) -> tuple[str | None, str | None]:
    """Parse a node's ``model:`` string into ``(profile, model_slug)`` for codex."""
    raw = (model or "").strip()
    if not raw:
        return None, None
    if "@" in raw:
        prof, _, slug = raw.partition("@")
        return (prof.strip() or None), (slug.strip() or None)
    return raw, None


def _on_event(event, state: TurnState, node_id):
    """Codex `exec --json`: thread.started → resume id; item.completed agent_message → answer text (last wins); turn.completed → token usage; error/failed → diagnostics."""
    etype = event.get("type") or ""
    if etype == "thread.started":
        state.session_id = event.get("thread_id") or state.session_id
    elif etype == "turn.completed":
        state.usage = state.usage.merge(_usage.normalize(event))
    elif etype == "item.completed":
        item = event.get("item") or {}
        if item.get("type") == "agent_message":
            text = item.get("text") or ""
            if text:
                state.result_text = text
                print(f"[{node_id}] {text.strip()[:500]}", flush=True)
        elif item.get("type") == "error" or item.get("error"):
            state.diagnostics.append(str(item)[:500])
    elif "error" in etype or "fail" in etype:
        state.diagnostics.append(json.dumps(event)[:500])


class CodexBackend(JsonlBackend):
    """OpenAI Codex CLI (``codex exec --json``)."""

    name = "codex"
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
        profile, model_slug = _parse_codex_model(model)
        if not profile:
            profile = (os.environ.get("CODEX_PROFILE") or "").strip() or None
        head = ["codex", *(["--profile", profile] if profile else [])]
        flags = [
            "--json",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if model_slug:
            flags += ["-m", model_slug]
        if effort:
            codex_effort = "high" if effort in ("xhigh", "max") else effort
            flags += ["-c", f'model_reasoning_effort="{codex_effort}"']
        if sid:
            cmd = [*head, "exec", "resume", *flags, sid, "-"]
            print(f"[{node_id}] 🔄 Resuming codex session: {sid[:8]}...", flush=True)
        else:
            cmd = [*head, "exec", *flags, "-"]
        state = self.stream(
            cmd, node_id, timeout, prompt, _on_event,
            resilience=resilience, cwd=cwd,
            env_extra=self.harness_env(),
        )
        return finalize_turn("codex", node_id, state, session_id_path, timeout)

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
