"""Claude Code CLI (``claude -p``) — its ``stream-json`` / ``--resume`` / ``/compact``
protocol, and the adapter that exposes it as an ``AgentBackend``.

This is the only place that knows Claude's event vocabulary. It used to live in
``runner/agent.py`` — the CLI-agnostic recovery ladder — with the backend facade
delegating back into it, which made the generic ring the home of one implementation
and forced ``agent`` and ``backends`` to import each other lazily. Claude is now a
sibling of every other adapter and the ladder imports it not at all.

Unlike the other CLIs, Claude compacts in place: ``/compact`` over ``--resume -p``
summarizes the conversation and keeps the session id, so the ladder can retry the
*same* prompt on a smaller session instead of reframing it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from workhorse import otel
from workhorse.config_run import AgentResilience
from workhorse.runner import agent as _agent
from workhorse.runner import usage as _usage
from workhorse.runner.backends import AgentBackend


class ClaudeBackend(AgentBackend):
    """Claude Code CLI (``claude -p``). Owns the protocol below; the resilience
    ladder sees only ``run_turn`` / ``compact``."""

    name = "claude"
    default_model = "sonnet"
    supports_compaction = True

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
        # Claude has a native reasoning-effort flag (`--effort low|medium|high|xhigh|max`).
        return _run_cli(
            prompt,
            node_id,
            session_id_path,
            model,
            resilience=resilience,
            timeout=timeout,
            cwd=cwd,
            add_dirs=add_dirs,
            effort=effort,
            env_extra=self.harness_env(),
        )

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ) -> bool:
        # Same harness, same environment: a knob that shapes the turn must also shape
        # the /compact turn, or compaction runs under a different CLI configuration
        # than the conversation it is compacting.
        return _compact_session(
            session_id_path,
            node_id,
            model,
            resilience=resilience,
            timeout=timeout,
            env_extra=self.harness_env(),
        )


def _run_cli(
    prompt: str,
    node_id: str,
    session_id_path: Path | None,
    model: str | None = None,
    *,
    resilience: AgentResilience,
    timeout: float,
    cwd: str | None = None,
    add_dirs: list[str] | None = None,
    effort: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> str:
    """Run a single Claude CLI turn for ``prompt``, returning the final result
    text. Raises ``BackendInvocationError`` (via ``classify_turn``) on CLI failure,
    classifying it as transient when the captured output matches a known retryable
    marker.

    Args:
        timeout: Maximum seconds to wait for a result event from the agent.
        cwd: Working directory for the subprocess (controls CLAUDE.md discovery).
        add_dirs: Additional directories to grant the agent access to.
        env_extra: Operator-configured extra environment for this harness
            (``[harness.claude].env``), layered over the inherited environment.
    """
    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if model:
        cmd.extend(["--model", model])
    if effort:
        cmd.extend(["--effort", effort])
    for d in (add_dirs or []):
        cmd.extend(["--add-dir", d])
    cmd.append("-p")

    # Resume session if one exists
    if session_id_path and session_id_path.exists():
        sid = session_id_path.read_text().strip()
        if sid:
            cmd.extend(["--resume", sid])
            print(f"[{node_id}] 🔄 Resuming session: {sid[:8]}...", flush=True)

    # Stream Claude's events through the shared supervised spawn path: own process
    # group, hard watchdog, and group-reaping kill all live in stream_subprocess, so the
    # timeout behaves identically here and in every other harness. The diagnostics string
    # captures non-event output (e.g. "Spending cap reached") and error-result subtypes
    # so the caller can classify transient failures.
    stream = _stream_events(
        cmd, node_id, timeout,
        resilience=resilience,
        stdin_data=prompt, cwd=cwd or None, env_extra=env_extra,
    )

    # Classify the finished turn through the one shared classifier so the Claude
    # path and every other backend produce identical messages and transient /
    # overflow / cap / non-recoverable verdicts. Claude's structured-cap signals
    # (rate_limited / rate_reset_at, from the stream-json rate_limit_event) are
    # passed in so a capped window still carries its precise reset epoch.
    return _agent.classify_turn(
        "claude",
        node_id,
        result_text=stream.result_text,
        diagnostics=stream.diagnostics_text,
        timed_out=stream.timed_out,
        returncode=stream.returncode,
        timeout=timeout,
        session_id=stream.session_id,
        session_id_path=session_id_path,
        rate_limited=stream.rate_limited,
        rate_reset_at=stream.rate_reset_at,
    )


def _compact_session(
    session_id_path: Path | None,
    node_id: str,
    model: str | None = None,
    *,
    resilience: AgentResilience,
    timeout: float,
    env_extra: dict[str, str] | None = None,
) -> bool:
    """Best-effort: resume the node's session and run the CLI's ``/compact`` command
    to summarize the conversation so far, freeing context so the node can continue
    on the same (now smaller) session.

    Persists the resulting session id so the next attempt resumes the compacted
    conversation. Returns True when compaction ran without itself overflowing;
    returns False (never raises) when there is no session to compact, the call
    fails, or ``/compact`` couldn't run within the window — callers then fall back
    to reframing.

    The headless CLI (verified on Claude Code 2.1.x) honors ``/compact`` in ``-p
    --resume`` mode and reports the outcome via ``system``/``status`` events:
    ``status: "compacting"`` then a terminal event carrying ``compact_result``
    ("success" / "failed", with ``compact_error``). The session id is preserved.
    We key success off ``compact_result`` (treating "started but no explicit
    failure" as success for forward-compat), and persist the session id so the
    retry resumes the compacted conversation.
    """
    if not (session_id_path and session_id_path.exists()):
        return False
    sid = session_id_path.read_text().strip()
    if not sid:
        return False

    cmd = [
        "claude",
        "--dangerously-skip-permissions",
        "--output-format", "stream-json",
        "--verbose",
    ]
    if model:
        cmd.extend(["--model", model])
    cmd.extend(["--resume", sid, "-p"])

    print(f"[{node_id}] 🗜 compacting session {sid[:8]}… to free context", flush=True)
    st = {"saw_compacting": False, "compact_failed": False, "compact_error": "",
          "new_session_id": sid}

    def on_line(raw: str) -> None:
        line = raw.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return
        if event.get("session_id"):
            st["new_session_id"] = event["session_id"]
        if event.get("status") == "compacting":
            st["saw_compacting"] = True
        if "compact_result" in event:
            if event.get("compact_result") == "failed":
                st["compact_failed"] = True
                st["compact_error"] = str(event.get("compact_error") or "")
            elif event.get("compact_result") == "success":
                st["saw_compacting"] = True

    try:
        # Shares the supervised spawn path (own process group, hard watchdog, group
        # reap), so a wedged /compact turn can't hang the run either.
        _agent.stream_subprocess(
            cmd, node_id, timeout, on_line,
            resilience=resilience,
            stdin_data="/compact", env_extra=env_extra,
        )
    except Exception as exc:  # noqa: BLE001 — compaction is best-effort
        print(f"[{node_id}] ⚠ compaction call failed: {exc}", flush=True)
        return False

    saw_compacting = st["saw_compacting"]
    compact_failed = st["compact_failed"]
    compact_error = st["compact_error"]
    new_session_id = st["new_session_id"]
    if new_session_id:
        session_id_path.write_text(new_session_id)

    if compact_failed:
        print(f"[{node_id}] ⚠ compaction failed: {compact_error}", flush=True)
        return False
    return saw_compacting


@dataclass(slots=True)
class ClaudeTurnStream:
    """What one Claude turn yielded, as its stream-json went past.

    Mutable by construction: the per-line callback writes into it event by event and
    the process outcome lands once the stream closes. It replaces a seven-element
    tuple every caller had to decode by counting positions.
    """

    result_text: str = ""
    session_id: str | None = None
    #: Anything signalling *how* a turn failed — non-event output lines (e.g.
    #: "Spending cap reached") and error-result subtypes — for ``classify_turn``.
    diagnostics: list[str] = field(default_factory=list)
    timed_out: bool = False
    #: True once any ``rate_limit_event`` reported the limit as hit.
    rate_limited: bool = False
    #: The most recent window-reset epoch seen, used only when the failure is
    #: otherwise determined to be a cap (for precise wait timing).
    rate_reset_at: float | None = None
    returncode: int = 0

    @property
    def diagnostics_text(self) -> str:
        """The diagnostics as the single string ``classify_turn`` scans."""
        return "\n".join(self.diagnostics)


def _stream_events(
    cmd: list[str],
    node_id: str,
    timeout: float,
    *,
    resilience: AgentResilience,
    stdin_data: str | None = None,
    cwd: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> ClaudeTurnStream:
    """Run ``cmd`` through the shared supervised spawn path and parse Claude's
    stream-json, echoing a concise live view to stdout. Returns the finished
    ``ClaudeTurnStream``.

    ``timed_out`` indicates the turn hit its deadline (in-loop or watchdog). The
    timeout/process-group kill all live in ``stream_subprocess`` — this function only
    interprets the lines."""
    stream = ClaudeTurnStream()

    def on_line(raw_line: str) -> None:
        line = raw_line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON line (e.g. merged stderr) — surface it so logs aren't silent
            # and keep it as a diagnostic for failure classification.
            print(f"[{node_id}] {line}", flush=True)
            stream.diagnostics.append(line)
            return

        etype = event.get("type")
        if etype == "result":
            stream.result_text = event.get("result", "") or stream.result_text
            # Attach the turn's duration + token usage to the open turn span so
            # per-node latency/cost attribution needs no artifact join. Normalized
            # through the same mapper every other backend uses, so one query shape
            # reads them all (workhorse/runner/usage.py). Unconditional: Claude's
            # result event carries `duration_ms` even when it reports no tokens.
            otel.turn_result(_usage.normalize(event))
            # An error result carries the reason in its subtype / is_error flag.
            if event.get("is_error") or event.get("subtype") not in (None, "success"):
                stream.diagnostics.append(
                    str(event.get("subtype") or "") + " " + str(event.get("result") or "")
                )
        elif etype == "rate_limit_event":
            blocked, reset_at = _agent._rate_limit_info(event)
            if reset_at is not None:
                stream.rate_reset_at = reset_at  # last-seen window reset (only if capped)
            if blocked:
                stream.rate_limited = True
        elif etype == "system" and "session_id" in event:
            stream.session_id = event["session_id"]
        _emit_event(node_id, event)

    stream.timed_out, stream.returncode = _agent.stream_subprocess(
        cmd, node_id, timeout, on_line,
        resilience=resilience,
        stdin_data=stdin_data, cwd=cwd, env_extra=env_extra,
    )
    return stream


def _emit_event(node_id: str, event: dict) -> None:
    """Print a concise, human-readable view of a Claude stream-json event."""
    etype = event.get("type")
    if etype == "assistant":
        for block in event.get("message", {}).get("content", []) or []:
            btype = block.get("type")
            if btype == "text":
                text = block.get("text", "").strip()
                if text:
                    print(f"[{node_id}] {text}", flush=True)
            elif btype == "tool_use":
                name = block.get("name", "?")
                line = f"[{node_id}] ⚙ {name} {_tool_summary(block.get('input', {}))}".rstrip()
                print(line, flush=True)
    elif etype == "result":
        dur = event.get("duration_ms")
        print(f"[{node_id}] ✓ result received" + (f" ({dur} ms)" if dur else ""), flush=True)


def _tool_summary(inp: dict) -> str:
    for key in ("file_path", "path", "command", "pattern", "url", "query", "description"):
        value = inp.get(key)
        if value:
            flat = " ".join(str(value).split())
            return flat[:120] + "…" if len(flat) > 120 else flat
    return ""
