"""Agent CLI backends — the facade that lets the controller drive different agent
CLIs (Claude, Codex, Copilot, Aider, OpenCode) behind one interface.

The resilience ladder in ``agent.py`` (transient/cap retries, context-overflow
compaction, prompt reframing, default-to-next) is CLI-agnostic and delegates the
two operations that ARE CLI-specific to the active backend:

* ``run_turn`` — run one non-interactive turn and return its final text.
* ``compact``  — best-effort context compaction (``False`` when unsupported, in
  which case the ladder reframes instead).

The backend is chosen per-run via the ``AGENT_CLI`` env var (or ``--cli``), so a
single workflow runs entirely on one CLI. The *model* is selectable per node via a
node's ``model:`` map (a per-CLI map, e.g. ``{claude: opus, aider: openrouter/...}``;
see ``runner/agent.py``). To run a node on an OpenRouter model, point an
OpenRouter-native backend (``aider`` / ``opencode``) at it with ``AGENT_CLI`` and
give the node an ``openrouter/<slug>`` model — no proxy, since those CLIs speak
plain chat-completions and (for the MiMo experiment) cache natively.

``ClaudeBackend`` is an *adapter* over the existing Claude functions in
``agent.py`` (``_run_claude_cli`` / ``_compact_session``): it calls them through
the ``agent`` module so they remain the single, tested implementation of the
Claude ``stream-json`` / ``--resume`` / ``/compact`` protocol. ``CodexBackend``
(``codex exec --json``), ``CopilotBackend`` (``copilot -p --output-format json``)
and ``OpenCodeBackend`` (``opencode run --format json``) implement their own JSONL
protocols here, sharing the ``_stream_jsonl`` event loop and ``_finalize_turn``
classifier below. ``AiderBackend`` (``aider --message``) has no event protocol —
it streams plain text, captured line-for-line by ``_run_text_turn`` and handed to
the same classifier. None of the non-Claude backends compact in place (they manage
context internally, or — aider — run a single message), so the ladder reframes on
overflow.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from pathlib import Path

# Import the module (not its names) so test monkeypatches of e.g.
# ``agent._run_claude_cli`` are resolved at call time. agent.py imports this
# module only lazily (inside run_agent/_invoke_claude), so there is no import cycle.
from workhorse.runner import agent as _agent


class AgentBackend(ABC):
    """One agent CLI behind a uniform interface. Stateless — safe to share."""

    #: Short name used in logs and the ``AGENT_CLI`` registry key.
    name: str = "agent"
    #: Model used when a node declares no ``model:`` and no env override is set.
    default_model: str | None = None
    #: Whether the CLI can compact a long session in place. When False the
    #: resilience ladder reframes on context overflow instead of compacting.
    supports_compaction: bool = False

    @abstractmethod
    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        """Run one non-interactive turn for ``prompt`` and return the final result
        text. Persist the session id (when the CLI supports resume) to
        ``session_id_path``. Raise ``agent.BackendInvocationError`` on failure,
        classifying it as ``transient`` / ``overflow`` / cap (``reset_at``) so the
        ladder can recover appropriately.

        ``cwd`` sets the subprocess working directory (controls CLAUDE.md/skills
        discovery). ``add_dirs`` are additional directories the agent can access
        (passed as --add-dir flags to Claude). ``effort`` is the node's reasoning
        effort ("low"/"medium"/"high"); each backend translates it (thinking
        directive for Claude/Copilot, ``model_reasoning_effort`` for Codex)."""

    @abstractmethod
    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
    ) -> bool:
        """Best-effort: compact the node's session to free context so it can
        continue. Return True when compaction ran, False when it could not (no
        session, failure) or is unsupported — callers then fall back to reframe."""


class ClaudeBackend(AgentBackend):
    """Claude Code CLI (``claude -p``). Adapter over the Claude implementation in
    ``agent.py`` — see this module's docstring for why it delegates rather than
    owning the protocol code."""

    name = "claude"
    default_model = "sonnet"
    supports_compaction = True

    def run_turn(
        self,
        prompt: str,
        node_id: str,
        session_id_path: Path | None,
        model: str | None = None,
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        # Claude has a native reasoning-effort flag (`--effort low|medium|high|xhigh|max`).
        return _agent._run_claude_cli(
            prompt,
            node_id,
            session_id_path,
            model,
            timeout=timeout,
            cwd=cwd,
            add_dirs=add_dirs,
            effort=effort,
        )

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
    ) -> bool:
        return _agent._compact_session(session_id_path, node_id, model)


# ── Shared JSONL plumbing for non-Claude backends ──────────────────────────────
# Codex and Copilot both stream newline-delimited JSON. The loop below is generic;
# each backend supplies an ``on_event`` callback that pulls the final answer text
# and the resumable session id out of its own event vocabulary into ``state``.


def _read_session_id(session_id_path: Path | None) -> str | None:
    """The persisted session id for this node, if any (for --resume)."""
    if session_id_path and session_id_path.exists():
        sid = session_id_path.read_text().strip()
        return sid or None
    return None


def _stream_jsonl(cmd, node_id, timeout, stdin_data, on_event, cwd=None):
    """Run ``cmd``, feed ``stdin_data`` (or nothing), and stream its JSONL stdout,
    invoking ``on_event(event, state, node_id, diagnostics)`` per parsed object.

    Streams through ``agent.stream_subprocess`` so the timeout, hard watchdog, and
    process-group kill behave identically to every other harness. ``cwd`` sets the
    subprocess working directory (previously silently dropped here, so Codex/Copilot/
    OpenCode nodes always ran in the launching process's CWD regardless of a node's
    ``cwd:``). Returns ``(state, diagnostics, timed_out, returncode)`` where ``state``
    carries ``result_text`` and ``session_id``. Non-JSON lines are echoed and kept as
    diagnostics so failure classification can see them."""
    state: dict = {"result_text": "", "session_id": None}
    diagnostics: list[str] = []
    early_abort = [""]

    def on_line(raw: str) -> bool:
        line = raw.strip()
        if not line:
            return False
        before = len(diagnostics)
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"[{node_id}] {line}", flush=True)
            diagnostics.append(line)
        else:
            on_event(event, state, node_id, diagnostics)
        # As soon as a recoverable provider failure appears — whether as a raw log
        # line or a structured error event — abort the CLI's internal retry loop and
        # hand recovery to Workhorse's bounded backoff policy. Caps retain their
        # separate scheduled-reset path. Scan only newly-added diagnostics so this
        # stays O(n) over the stream.
        new_diag = "\n".join(diagnostics[before:])
        if not early_abort[0] and new_diag and _agent._is_cap(new_diag):
            early_abort[0] = "cap"
            return True  # signal stream_subprocess to break and kill the process
        if not early_abort[0] and new_diag and _agent._is_transient(new_diag):
            early_abort[0] = "transient"
            return True  # signal stream_subprocess to break and kill the process
        return False

    timed_out, returncode = _agent.stream_subprocess(
        cmd, node_id, timeout, on_line, stdin_data=stdin_data, cwd=cwd
    )
    return state, "\n".join(diagnostics), timed_out or bool(early_abort[0]), returncode


def _finalize_turn(
    backend_name,
    node_id,
    state,
    diagnostics,
    timed_out,
    returncode,
    session_id_path,
    timeout=_agent.DEFAULT_RESULT_TIMEOUT_S,
    rate_reset_at=None,
) -> str:
    """Classify a finished turn through the one shared classifier, so the JSONL/text
    backends and the Claude path produce identical failure messages and transient /
    overflow / non-recoverable verdicts. See ``agent.classify_turn``.

    ``rate_reset_at`` is an optional unix epoch when a cap's window reopens (the
    opencode/Codex path fetches it out-of-band); on a cap the classifier attaches it
    so the runner sleeps until exactly then instead of the blind default wait."""
    return _agent.classify_turn(
        backend_name,
        node_id,
        result_text=state.get("result_text"),
        diagnostics=diagnostics,
        timed_out=timed_out,
        returncode=returncode,
        timeout=timeout,
        session_id=state.get("session_id"),
        session_id_path=session_id_path,
        rate_reset_at=rate_reset_at,
    )


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


def _codex_on_event(event, state, node_id, diagnostics):
    """Codex `exec --json`: thread.started → resume id; item.completed agent_message
    → answer text (last wins); anything error/failed → diagnostics."""
    etype = event.get("type") or ""
    if etype == "thread.started":
        state["session_id"] = event.get("thread_id") or state["session_id"]
    elif etype == "item.completed":
        item = event.get("item") or {}
        if item.get("type") == "agent_message":
            text = item.get("text") or ""
            if text:
                state["result_text"] = text
                print(f"[{node_id}] {text.strip()[:500]}", flush=True)
        elif item.get("type") == "error" or item.get("error"):
            diagnostics.append(str(item)[:500])
    elif "error" in etype or "fail" in etype:
        diagnostics.append(json.dumps(event)[:500])


def _copilot_on_event(event, state, node_id, diagnostics):
    """Copilot `-p --output-format json`: assistant.message.data.content → answer
    text (last non-empty wins); result → sessionId + exitCode."""
    etype = event.get("type") or ""
    if etype == "assistant.message":
        content = (event.get("data") or {}).get("content") or ""
        if content:
            state["result_text"] = content
            print(f"[{node_id}] {content.strip()[:500]}", flush=True)
    elif etype == "result":
        if event.get("sessionId"):
            state["session_id"] = event["sessionId"]
        exit_code = event.get("exitCode")
        if exit_code not in (0, None):
            diagnostics.append(f"copilot exitCode={exit_code}")
    elif "error" in etype:
        diagnostics.append(json.dumps(event)[:500])


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
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        sid = _read_session_id(session_id_path)
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
        state, diag, timed_out, rc = _stream_jsonl(
            cmd, node_id, timeout, prompt, _codex_on_event, cwd=cwd
        )
        return _finalize_turn(
            "codex", node_id, state, diag, timed_out, rc, session_id_path, timeout
        )

    def compact(
        self,
        session_id_path,
        node_id,
        model=None,
        timeout=_agent.DEFAULT_RESULT_TIMEOUT_S,
    ):
        return False


class CopilotBackend(AgentBackend):
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
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        sid = _read_session_id(session_id_path)
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
        state, diag, timed_out, rc = _stream_jsonl(
            cmd, node_id, timeout, None, _copilot_on_event, cwd=cwd
        )
        return _finalize_turn(
            "copilot", node_id, state, diag, timed_out, rc, session_id_path, timeout
        )

    def compact(
        self,
        session_id_path,
        node_id,
        model=None,
        timeout=_agent.DEFAULT_RESULT_TIMEOUT_S,
    ):
        return False


def _opencode_on_event(event, state, node_id, diagnostics):
    """OpenCode `run --format json`: NDJSON events with a top-level ``type`` and
    ``sessionID``. ``text`` parts carry the answer (``part.text``); we accumulate
    them keyed by part id so multiple text blocks are preserved in order. ``error``
    events go to diagnostics. The top-level ``sessionID`` is the resume handle."""
    sid = event.get("sessionID")
    if sid:
        state["session_id"] = sid
    etype = event.get("type") or ""
    if etype == "text":
        part = event.get("part") or {}
        text = part.get("text") or ""
        if text:
            parts = state.setdefault("_text_parts", {})
            parts[part.get("id") or len(parts)] = text
            state["result_text"] = "\n".join(parts.values())
            print(f"[{node_id}] {text.strip()[:500]}", flush=True)
    elif etype == "error":
        err = event.get("error") or {}
        data = err.get("data") or {}
        msg = data.get("message") or err.get("name") or json.dumps(event)[:300]
        diagnostics.append(str(msg)[:500])


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


class OpenCodeBackend(AgentBackend):
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
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
    ) -> str:
        sid = _read_session_id(session_id_path)
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
        state, diag, timed_out, rc = _stream_jsonl(
            cmd, node_id, timeout, None, _opencode_on_event, cwd=cwd
        )
        # On a Codex usage cap, fetch the precise reset epoch (opencode hides it on the
        # headless path) so the runner sleeps until the window reopens, not a flat hour.
        rate_reset_at = _codex_reset_at(model) if _agent._is_cap(diag) else None
        return _finalize_turn(
            "opencode",
            node_id,
            state,
            diag,
            timed_out,
            rc,
            session_id_path,
            timeout,
            rate_reset_at=rate_reset_at,
        )

    def compact(
        self,
        session_id_path,
        node_id,
        model=None,
        timeout=_agent.DEFAULT_RESULT_TIMEOUT_S,
    ):
        return False


def _run_text_turn(backend_name, cmd, node_id, timeout, cwd, session_id_path):
    """Run a NON-JSONL agent CLI (aider) that streams plain text to stdout: echo and
    accumulate every line as the turn result. Mirrors ``_stream_jsonl``'s timeout /
    live-echo loop, but these CLIs have no event protocol and no resumable session id
    — the whole transcript IS the result, and also the diagnostics channel (overflow
    / transient markers are printed inline, so ``_finalize_turn`` classifies off it).

    Streams through ``agent.stream_subprocess`` so the timeout, hard watchdog, and
    process-group kill behave identically to every other harness."""
    lines: list[str] = []

    def on_line(raw: str) -> None:
        line = raw.rstrip("\n")
        print(f"[{node_id}] {line}", flush=True)
        lines.append(line)

    timed_out, returncode = _agent.stream_subprocess(
        cmd, node_id, timeout, on_line, cwd=cwd
    )
    text = "\n".join(lines).strip()
    state = {"result_text": text, "session_id": None}
    return _finalize_turn(
        backend_name,
        node_id,
        state,
        text,
        timed_out,
        returncode,
        session_id_path,
        timeout,
    )


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
        timeout: float = _agent.DEFAULT_RESULT_TIMEOUT_S,
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
        return _run_text_turn("aider", cmd, node_id, timeout, cwd, session_id_path)

    def compact(
        self,
        session_id_path,
        node_id,
        model=None,
        timeout=_agent.DEFAULT_RESULT_TIMEOUT_S,
    ):
        return False


# Registry of available backends, keyed by their AGENT_CLI name.
_REGISTRY: dict[str, type[AgentBackend]] = {
    "claude": ClaudeBackend,
    "codex": CodexBackend,
    "copilot": CopilotBackend,
    "aider": AiderBackend,
    "opencode": OpenCodeBackend,
}

_CACHE: dict[str, AgentBackend] = {}


def get_backend(name: str | None = None) -> AgentBackend:
    """Resolve the active backend: explicit ``name`` → ``AGENT_CLI`` env → ``claude``.

    Backends are stateless, so a per-name cached instance is reused. Raises
    ``ValueError`` (fail fast) on an unknown name."""
    resolved = (name or os.environ.get("AGENT_CLI") or "claude").strip().lower()
    if resolved not in _REGISTRY:
        available = ", ".join(sorted(_REGISTRY))
        raise ValueError(
            f"unknown CLI backend {resolved!r} (set AGENT_CLI to one of: {available})"
        )
    if resolved not in _CACHE:
        _CACHE[resolved] = _REGISTRY[resolved]()
    return _CACHE[resolved]
