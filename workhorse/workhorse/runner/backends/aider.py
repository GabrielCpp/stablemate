"""Aider (``aider --message``) — a plain-text, single-message CLI and its adapter.

Aider has no event protocol and no resumable session, so the turn loop it needs is
its own: the whole stdout transcript is both the answer and the diagnostics channel.
That loop lives here rather than beside ``stream_jsonl`` because aider is its only
user — a shared module holding one implementation's mechanics is the shape the port
package must not have.
"""

from __future__ import annotations

from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import process as _process
from workhorse.runner import usage as _usage
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn


def _run_text_turn(
    backend_name, cmd, node_id, timeout, cwd, session_id_path, *, resilience, env_extra=None
):
    """Run a NON-JSONL agent CLI (aider) that streams plain text to stdout: echo and
    accumulate every line as the turn result. Mirrors ``stream_jsonl``'s timeout /
    live-echo loop, but these CLIs have no event protocol and no resumable session id
    — the whole transcript IS the result, and also the diagnostics channel (overflow
    / transient markers are printed inline, so ``finalize_turn`` classifies off it).

    Streams through ``process.stream_subprocess`` so the timeout, hard watchdog, and
    process-group kill behave identically to every other harness."""
    lines: list[str] = []

    def on_line(raw: str) -> None:
        line = raw.rstrip("\n")
        print(f"[{node_id}] {line}", flush=True)
        lines.append(line)

    timed_out, returncode = _process.stream_subprocess(
        cmd, node_id, timeout, on_line,
        resilience=resilience, cwd=cwd, env_extra=env_extra,
    )
    text = "\n".join(lines).strip()
    state = TurnState(
        result_text=text,
        # The transcript is both the answer and the diagnostics channel: overflow and
        # transient markers are printed inline, so `classify_turn` scans the same text.
        diagnostics=[text],
        # A text backend has no event to carry usage, so the transcript is the only
        # source: aider prints a "Tokens: … Cost: …" summary. No match → no attributes.
        usage=_usage.from_text(text),
        timed_out=timed_out,
        returncode=returncode,
    )
    return finalize_turn(backend_name, node_id, state, session_id_path, timeout)


# Aider tops out at "high" for reasoning effort; clamp the Claude-superset levels.
def _aider_effort(effort: str) -> str:
    return "high" if effort in ("xhigh", "max") else effort


class AiderBackend(AgentBackend):
    """Aider (``aider --message``). A single-message, non-interactive coder that
    speaks plain chat-completions via litellm, so it drives OpenRouter models
    directly (``--model openrouter/xiaomi/mimo-v2.5``) with no proxy. Unlike the
    JSONL backends it has no event stream and no resumable session — each turn is a
    fresh ``--message`` whose full stdout transcript is the result; the resilience
    ladder reframes (never compacts/resumes) on failure. The OpenRouter provider pin
    + prompt caching for the MiMo experiment live in aider's own model-settings file,
    not here. ``add_dirs`` has no aider equivalent (it works the repo at ``cwd``) and
    is ignored."""

    name = "aider"
    default_model = None  # aider has no usable default; the node must name a model
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
        # Fully non-interactive: --yes-always answers every prompt; --no-stream/
        # --no-pretty give clean line-buffered output; --no-auto-commits/--no-gitignore
        # keep aider from mutating the repo's git state or .gitignore behind our back.
        cmd = [
            "aider",
            "--message",
            prompt,
            "--yes-always",
            "--no-stream",
            "--no-pretty",
            "--no-auto-commits",
            "--no-gitignore",
            "--no-analytics",
            "--no-show-model-warnings",
            "--no-check-model-accepts-settings",
        ]
        if model:
            cmd += ["--model", model]
        if effort:
            cmd += ["--reasoning-effort", _aider_effort(effort)]
        return _run_text_turn(
            "aider", cmd, node_id, timeout, cwd, session_id_path,
            resilience=resilience,
            env_extra=self.harness_env(),
        )

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
