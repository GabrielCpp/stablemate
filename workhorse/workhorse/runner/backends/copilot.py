"""GitHub Copilot CLI (``copilot -p --output-format json``) — event vocabulary and adapter."""

from __future__ import annotations

import json
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import usage as _usage
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id


def _on_event(event, state: TurnState, node_id):
    """Copilot `-p --output-format json`: assistant.message.data.content → answer
    text (last non-empty wins); result → sessionId + exitCode."""
    etype = event.get("type") or ""
    if etype == "assistant.message":
        content = (event.get("data") or {}).get("content") or ""
        if content:
            state.result_text = content
            print(f"[{node_id}] {content.strip()[:500]}", flush=True)
    elif etype == "result":
        if event.get("sessionId"):
            state.session_id = event["sessionId"]
        # Copilot's usage shape is unverified here (see usage.py), so this leans on
        # the tolerant search: if the result event carries counts anywhere, they are
        # found; if not, the turn keeps engine-measured duration and nothing else.
        state.usage = state.usage.merge(_usage.normalize(event))
        exit_code = event.get("exitCode")
        if exit_code not in (0, None):
            state.diagnostics.append(f"copilot exitCode={exit_code}")
    elif "error" in etype:
        state.diagnostics.append(json.dumps(event)[:500])


class CopilotBackend(JsonlBackend):
    """GitHub Copilot CLI (``copilot -p --output-format json``). No in-place
    compaction. --allow-all-tools + --no-ask-user make it fully autonomous (the
    container is the sandbox). Session is resumed by id via --session-id.
    ``add_dirs`` maps to one --add-dir per directory: Copilot's own path sandbox
    only allows CWD + subdirs + the temp dir by default, so multi-repo dispatch
    (a node whose cwd is one service repo but that also needs to read/write a
    sibling repo) needs this explicitly granted."""

    name = "copilot"
    default_model = None  # 'auto' / Copilot's default unless a node sets model
    supports_compaction = False

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        sid = read_session_id(session_id_path)
        # Copilot takes the prompt as a --prompt arg (no stdin prompt channel).
        cmd = [
            "copilot",
            "-p",
            prompt,
            "--output-format",
            "json",
            "--allow-all",
            "--no-ask-user",
        ]
        # --add-dir serves dual purpose for Copilot: path sandbox allowlisting AND
        # skill/CLAUDE.md discovery scope. Even with --allow-all (no sandbox), the
        # dirs inform Copilot where to look for project instructions.
        if model:
            cmd += ["--model", model]
        # Copilot has a native reasoning-effort flag (same level range as Claude).
        if effort:
            cmd += ["--effort", effort]
        # Grant access to sibling repos (multi-repo dispatch): Copilot's own path
        # sandbox only allows CWD + subdirs + temp dir by default.
        for d in add_dirs or []:
            cmd += ["--add-dir", d]
        if sid:
            cmd += ["--session-id", sid]
            print(f"[{node_id}] 🔄 Resuming copilot session: {sid[:8]}...", flush=True)
        state = self.stream(
            cmd, node_id, timeout, None, _on_event,
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
