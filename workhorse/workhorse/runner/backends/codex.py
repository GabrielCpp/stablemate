"""OpenAI Codex CLI (``codex exec --json``) — its event vocabulary and its adapter."""

from __future__ import annotations

import json
import os
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import usage as _usage
from workhorse.runner.backends import AgentBackend
from workhorse.runner.backends.jsonl import stream_jsonl
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id


def _parse_codex_model(model: str | None) -> tuple[str | None, str | None]:
    """Parse a node's ``model:`` string into ``(profile, model_slug)`` for codex.

    Codex's per-node selection is overloaded onto the generic ``model`` field as
    ``<profile>[@<model-slug>]``. ``@`` is the delimiter because it never appears
    in OpenRouter slugs (``deepseek/deepseek-chat-v3.1``) or local tags
    (``qwen2.5-coder:32b``), which freely use ``/`` and ``:``:

    * ``"local"``                         → profile=local,      model=None  (profile pins the model)
    * ``"openrouter@deepseek/deep-v3.1"`` → profile=openrouter, model=deepseek/deep-v3.1
    * ``"openrouter@"``                   → profile=openrouter, model=None
    * ``"@gpt-5.5"``                      → profile=None,        model=gpt-5.5  (model only; profile from CODEX_PROFILE)
    * ``""`` / ``None``                   → (None, None)

    A bare token (no ``@``) is a *profile* name — that is the unit codex configs
    bundle provider+auth+model into. To target a model on the default provider
    with no profile, lead with ``@``."""
    raw = (model or "").strip()
    if not raw:
        return None, None
    if "@" in raw:
        prof, _, slug = raw.partition("@")
        return (prof.strip() or None), (slug.strip() or None)
    return raw, None


def _on_event(event, state: TurnState, node_id):
    """Codex `exec --json`: thread.started → resume id; item.completed agent_message
    → answer text (last wins); turn.completed → token usage; error/failed →
    diagnostics."""
    etype = event.get("type") or ""
    if etype == "thread.started":
        state.session_id = event.get("thread_id") or state.session_id
    elif etype == "turn.completed":
        # Carries `usage` only — codex under subscription auth reports no cost, so
        # these turns land with tokens and no dollars (see usage.normalize).
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


class CodexBackend(AgentBackend):
    """OpenAI Codex CLI (``codex exec --json``). No in-place compaction — Codex
    manages its own context, so the ladder reframes on overflow. Runs with the
    sandbox bypassed because the worker container is itself the sandbox (mirrors
    Claude's --dangerously-skip-permissions).

    Per-node provider/model selection is overloaded onto the node ``model:`` field
    as ``<profile>[@<model-slug>]`` (see ``_parse_codex_model``), where the profile
    is a ``~/.codex/config.toml`` profile (e.g. ``openrouter``, ``local``). The
    ``CODEX_PROFILE`` env var is the run-level fallback when a node names none."""

    name = "codex"
    default_model = None  # use Codex's configured default unless a node sets model
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
        # Resolve a codex config *profile* (from ~/.codex/config.toml — selects the
        # provider, auth and a pinned model as one bundle) and an optional model
        # override, per node. `--profile` is a top-level flag (it must precede
        # `exec`, and `exec resume` doesn't accept it) so it goes in `head`; the
        # model override maps to `-m`.
        profile, model_slug = _parse_codex_model(model)
        if not profile:  # node didn't name one → fall back to the run-level default
            profile = (os.environ.get("CODEX_PROFILE") or "").strip() or None
        head = ["codex", *(["--profile", profile] if profile else [])]
        flags = [
            "--json",
            "--skip-git-repo-check",
            "--dangerously-bypass-approvals-and-sandbox",
        ]
        if model_slug:
            flags += ["-m", model_slug]
        # Codex has a native reasoning-effort knob (GPT-5.x); set it via a `-c` config
        # override (TOML value, hence the quotes). Codex tops out at "high", so clamp
        # the Claude-superset levels (xhigh/max) down to it.
        if effort:
            codex_effort = "high" if effort in ("xhigh", "max") else effort
            flags += ["-c", f'model_reasoning_effort="{codex_effort}"']
        if sid:
            # codex [--profile P] exec resume <flags> <session_id> -   (prompt on stdin)
            cmd = [*head, "exec", "resume", *flags, sid, "-"]
            print(f"[{node_id}] 🔄 Resuming codex session: {sid[:8]}...", flush=True)
        else:
            cmd = [*head, "exec", *flags, "-"]
        state = stream_jsonl(
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
