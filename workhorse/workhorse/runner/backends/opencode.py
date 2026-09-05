"""OpenCode CLI (``opencode run --format json``) — event vocabulary, adapter, and the
out-of-band probe for the ChatGPT/Codex provider's usage-window reset."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from workhorse.config_run import AgentResilience
from workhorse.runner import failure as _failure
from workhorse.runner import usage as _usage
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id


@dataclass(slots=True)
class _OpenCodeEvents:
    """OpenCode's per-turn event reader, and the text parts it has to remember.

    It is a class only because it has state no other backend has: opencode streams
    the answer as several ``text`` parts that must be reassembled in arrival order.
    That belongs to this adapter, not on the ``TurnState`` every backend shares — a
    struct shared by N implementations holding one implementation's private key is
    exactly the shape the shared module must not have. One instance per turn; the
    bound ``on_event`` is what the stream loop is handed.
    """

    #: part id → text. Ids come from opencode; the positional fallback keeps parts
    #: distinct (and in order) if an event ever arrives without one.
    parts: dict[str | int, str] = field(default_factory=dict)

    def on_event(self, event, state: TurnState, node_id) -> None:
        """OpenCode `run --format json`: NDJSON events with a top-level ``type`` and
        ``sessionID``. ``text`` parts carry the answer (``part.text``); we accumulate
        them keyed by part id so multiple text blocks are preserved in order.
        ``error`` events go to diagnostics. The top-level ``sessionID`` is the resume
        handle."""
        sid = event.get("sessionID")
        if sid:
            state.session_id = sid
        etype = event.get("type") or ""
        if etype == "step_finish":
            # One per step, not per turn: a turn that calls three tools emits three,
            # and only their sum is what the turn consumed. `part.cost` is 0 on
            # subscription auth — a real zero, which merge() keeps distinct from
            # "not reported".
            state.usage = state.usage.merge(_usage.normalize(event))
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


# OpenCode's `--variant` is its provider-specific reasoning knob; its documented
# levels are minimal/high/max, so map the Claude-superset effort onto those (medium
# has no opencode variant → leave it unset).
_OPENCODE_VARIANT = {"low": "minimal", "high": "high", "xhigh": "max", "max": "max"}


# opencode's openai provider is the ChatGPT/Codex OAuth backend. Every response from
# it carries the subscription's rate-limit state in `x-codex-*` headers — including
# `x-codex-primary-reset-at`, the unix epoch when the (5-hour) usage window reopens —
# and these ride along even on the 429 that reports "The usage limit has been reached".
# opencode reads them for its TUI percentage but DROPS them on the headless `run` path,
# so the runner never sees a reset time and falls back to the blind default wait. We
# read them ourselves, from the very same OAuth token opencode uses, so a Codex cap is
# waited out until its ACTUAL reset (like Claude's structured rate_limit_event) instead
# of re-probing on a fixed timer. Mirrors codex CLI's own usage display.
_CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
_OPENCODE_AUTH_PATH = Path(
    os.environ.get(
        "OPENCODE_AUTH_PATH", str(Path.home() / ".local/share/opencode/auth.json")
    )
)


def _codex_reset_at(model: str | None, timeout: float = 15.0) -> float | None:
    """Best-effort unix epoch when the ChatGPT/Codex usage window for ``model`` resets.

    Returns ``x-codex-primary-reset-at`` from the Codex backend, or ``None`` on ANY
    problem (disabled, non-codex model, missing/expired OAuth, network/parse error) —
    the caller then falls back to the default cap wait, so this can only ever sharpen
    the wait, never break the run. Gated to ``openai/*`` models (the Codex provider);
    OpenRouter caps on opencode go through the daily-key-limit path instead.

    Set ``WORKHORSE_CODEX_RESET_PROBE=0`` to disable the probe entirely.
    """
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
        # A minimal request: when capped it 429s WITH the reset headers and bills
        # nothing; the headers are what we're after, not any completion.
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
            resp.close()  # don't drain the stream — we only need the headers
        except urllib.error.HTTPError as exc:
            headers = exc.headers  # the 429 (cap) carries the same x-codex-* headers
        raw = headers.get("x-codex-primary-reset-at")
        return float(raw) if raw else None
    except Exception:
        return None


class OpenCodeBackend(JsonlBackend):
    """OpenCode CLI (``opencode run --format json``). Speaks plain chat-completions
    to whatever provider its model names, so it drives OpenRouter models directly —
    e.g. ``openrouter/xiaomi/mimo-v2.5`` — with no proxy. The prompt is passed as the
    positional message (after ``--`` so a leading dash can't be read as a flag);
    sessions resume by id via ``--session``. No in-place compaction."""

    name = "opencode"
    default_model = (
        None  # node/AGENT_MODEL names the provider/model (e.g. openrouter/…)
    )
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
        # --print-logs routes ERROR-level logs to stderr (merged into stdout by stream_subprocess),
        # so quota/limit errors like "The usage limit has been reached" appear as non-JSON lines in
        # diagnostics. The existing _is_cap() check then catches "usage limit" and triggers the
        # cap-wait path instead of burning the short-retry budget. Without this flag these logs
        # go only to ~/.local/share/opencode/log/opencode.log and workhorse never sees them —
        # opencode's internal exponential backoff runs silently until the watchdog kills it.
        cmd = [
            "opencode",
            "--print-logs",
            "--log-level",
            "ERROR",
            "run",
            "--format",
            "json",
            "--thinking",
        ]
        if model:
            cmd += ["-m", model]
        if effort and _OPENCODE_VARIANT.get(effort):
            cmd += ["--variant", _OPENCODE_VARIANT[effort]]
        if sid:
            cmd += ["--session", sid]
            print(f"[{node_id}] 🔄 Resuming opencode session: {sid[:8]}...", flush=True)
        # `--` ends option parsing so a prompt starting with '-' is still the message.
        cmd += ["--", prompt]
        # OpenCode reads the message from argv (no stdin prompt channel), so pass
        # nothing on stdin.
        # opencode's internal title/summary helper reads `small_model` from config —
        # there is no CLI flag — so without a pin it rides whatever the machine's
        # opencode.jsonc says, on whatever provider that names. A helper routed to a
        # provider the run doesn't otherwise use fails on that provider's own wall
        # (an OpenRouter credit exhaustion on the title call classified as a cap on
        # the node and slept a run for 6 days while its coding models were fine).
        # OPENCODE_CONFIG_CONTENT merges over the user config with highest
        # precedence, so pin the helper to the turn's own model. An operator who
        # sets OPENCODE_CONFIG_CONTENT in [harness.opencode].env has taken over the
        # whole inline config; their value passes through verbatim.
        env_extra = self.harness_env()
        if model and "OPENCODE_CONFIG_CONTENT" not in env_extra:
            env_extra = {
                "OPENCODE_CONFIG_CONTENT": json.dumps({"small_model": model}),
                **env_extra,
            }
        state = self.stream(
            cmd, node_id, timeout, None, _OpenCodeEvents().on_event,
            resilience=resilience, cwd=cwd,
            env_extra=env_extra,
        )
        # On a Codex usage cap, fetch the precise reset epoch (opencode hides it on the
        # headless path) so the runner sleeps until the window reopens, not a flat hour.
        rate_reset_at = (
            _codex_reset_at(model) if _failure.is_cap(state.diagnostics_text) else None
        )
        return finalize_turn(
            "opencode",
            node_id,
            state,
            session_id_path,
            timeout,
            rate_reset_at=rate_reset_at,
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
