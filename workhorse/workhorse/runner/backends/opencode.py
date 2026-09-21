"""OpenCode CLI (``opencode run --format json``) — event vocabulary, adapter, and the out-of-band probe for the ChatGPT/Codex provider's usage-window reset."""

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
from workhorse.runner.backends import ensure_prompt_is_not_in_argv, prepare_argv_prompt
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import TurnState, finalize_turn, read_session_id


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


_OPENCODE_VARIANT = {"low": "minimal", "high": "high", "xhigh": "max", "max": "max"}

_OPENCODE_OUTPUT_TOKEN_MAX_ENV = "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"
_OPENCODE_OUTPUT_TOKEN_MAX = "131072"


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
        argv_prompt, attachment = prepare_argv_prompt(prompt, prompt_path)
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
        if attachment is not None:
            cmd += ["--file", str(attachment)]
        cmd += ["--", argv_prompt]
        ensure_prompt_is_not_in_argv(prompt, cmd)
        env_extra = self.harness_env()
        if model and "OPENCODE_CONFIG_CONTENT" not in env_extra:
            env_extra = {
                "OPENCODE_CONFIG_CONTENT": json.dumps({"small_model": model}),
                **env_extra,
            }
        if _OPENCODE_OUTPUT_TOKEN_MAX_ENV not in env_extra:
            env_extra = {
                _OPENCODE_OUTPUT_TOKEN_MAX_ENV: _OPENCODE_OUTPUT_TOKEN_MAX,
                **env_extra,
            }
        state = self.stream(
            cmd, node_id, timeout, None, _OpenCodeEvents().on_event,
            resilience=resilience, cwd=cwd,
            env_extra=env_extra,
        )
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
