"""Claude Code CLI (``claude -p``) — its ``stream-json`` / ``--resume`` / ``/compact`` protocol, and the adapter that exposes it as an ``AgentBackend``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from workhorse import otel, reload
from workhorse.config_run import AgentResilience
from workhorse.runner import failure as _failure
from workhorse.runner import process as _process
from workhorse.runner import usage as _usage
from workhorse.runner.backends import AgentBackend, AgentProfile, git_worktree


class ClaudeBackend(AgentBackend):
    """Claude Code CLI (``claude -p``)."""

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
        prompt_path: Path | None = None,
        timeout: float,
        resilience: AgentResilience,
        cwd: str | None = None,
        add_dirs: list[str] | None = None,
        effort: str | None = None,
        agent: AgentProfile | None = None,
    ) -> str:
        """Run one Claude CLI turn and return its final result text."""
        cmd = [
            "claude",
            *_permission_flags(agent),
            "--output-format", "stream-json",
            "--verbose",
            "--disallowedTools", "Agent",
            *_tool_flags(agent),
        ]
        if model:
            cmd.extend(["--model", model])
        if effort:
            cmd.extend(["--effort", effort])
        for directory in [*(add_dirs or []), *_skill_dirs(agent, cwd)]:
            cmd.extend(["--add-dir", directory])
        cmd.append("-p")

        if session_id_path and session_id_path.exists():
            sid = session_id_path.read_text().strip()
            if sid:
                cmd.extend(["--resume", sid])
                print(f"[{node_id}] 🔄 Resuming session: {sid[:8]}...", flush=True)

        stream = _stream_events(
            cmd,
            node_id,
            timeout,
            resilience=resilience,
            stdin_data=prompt,
            cwd=cwd or None,
            env_extra=self.harness_env(),
        )

        return _failure.classify_turn(
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

    def compact(
        self,
        session_id_path: Path | None,
        node_id: str,
        model: str | None = None,
        *,
        timeout: float,
        resilience: AgentResilience,
    ) -> bool:
        """Resume the node's session and ask Claude to compact its context."""
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
        st = {
            "saw_compacting": False,
            "compact_failed": False,
            "compact_error": "",
            "new_session_id": sid,
        }

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
            _process.stream_subprocess(
                cmd,
                node_id,
                timeout,
                on_line,
                resilience=resilience,
                stdin_data="/compact",
                env_extra=self.harness_env(),
            )
        except reload.ReloadRequested:
            raise
        except Exception as exc:  # noqa: BLE001 — compaction is best-effort
            print(f"[{node_id}] ⚠ compaction call failed: {exc}", flush=True)
            return False

        new_session_id = st["new_session_id"]
        if new_session_id:
            session_id_path.write_text(new_session_id)

        if st["compact_failed"]:
            print(f"[{node_id}] ⚠ compaction failed: {st['compact_error']}", flush=True)
            return False
        return st["saw_compacting"]


_CONFINED_TOOLS = ("Skill", "Read", "Edit", "Write", "Glob", "Grep")
_SKILL_DIR = ".claude/skills"


def _permission_flags(agent: AgentProfile | None) -> list[str]:
    """Skip every permission prompt, or for a confined profile refuse whatever its rules do not allow.

    Under `dontAsk` the CLI allows reads inside the cwd and the added directories and
    denies every other call no rule allows. Only the project's settings are loaded, so
    an operator's own allow rules cannot widen the turn.
    """
    if agent is None or not agent.confined:
        return ["--dangerously-skip-permissions"]
    return ["--permission-mode", "dontAsk", "--setting-sources", "project"]


def _skill_dirs(agent: AgentProfile | None, cwd: str | None) -> list[str]:
    """The project skill directory a confined turn may read, since the skills it loads are files it opens."""
    if agent is None or not agent.confined:
        return []
    worktree = git_worktree(Path(cwd or os.getcwd()).resolve())
    if worktree is None:
        return []
    skills = worktree / _SKILL_DIR
    return [str(skills)] if skills.is_dir() else []


def _tool_flags(agent: AgentProfile | None) -> list[str]:
    """The flags that narrow a turn to its profile's tools: `--tools` and no MCP server when `*` is off, else a deny list."""
    tools = agent.tools if agent else {}
    named = {name: on for name, on in tools.items() if name != "*"}
    if agent is not None and agent.confined:
        shell = ["Bash"] if agent.commands else []
        enabled = dict.fromkeys([*_CONFINED_TOOLS, *shell, *(name for name, on in named.items() if on)])
        allowed = ["Edit(./**)", *(rule for command in agent.commands for rule in (f"Bash({command})", f"Bash({command} *)"))]
        return ["--tools", ",".join(enabled), "--strict-mcp-config", "--allowedTools", *allowed]
    if tools.get("*") is False:
        return ["--tools", ",".join(name for name, on in named.items() if on), "--strict-mcp-config"]
    denied = [name for name, on in named.items() if not on]
    return ["--disallowedTools", *denied] if denied else []


@dataclass(slots=True)
class ClaudeTurnStream:
    """What one Claude turn yielded, as its stream-json went past."""

    result_text: str = ""
    session_id: str | None = None
    diagnostics: list[str] = field(default_factory=list)
    timed_out: bool = False
    rate_limited: bool = False
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
    """Run ``cmd`` through the shared supervised spawn path and parse Claude's stream-json, echoing a concise live view to stdout."""
    stream = ClaudeTurnStream()

    def on_line(raw_line: str) -> None:
        line = raw_line.strip()
        if not line:
            return
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            print(f"[{node_id}] {line}", flush=True)
            stream.diagnostics.append(line)
            return

        etype = event.get("type")
        if etype == "result":
            stream.result_text = event.get("result", "") or stream.result_text
            otel.turn_result(_usage.normalize(event))
            if event.get("is_error") or event.get("subtype") not in (None, "success"):
                stream.diagnostics.append(
                    str(event.get("subtype") or "") + " " + str(event.get("result") or "")
                )
        elif etype == "rate_limit_event":
            blocked, reset_at = _failure.rate_limit_info(event)
            if reset_at is not None:
                stream.rate_reset_at = reset_at
            if blocked:
                stream.rate_limited = True
        elif etype == "system" and "session_id" in event:
            stream.session_id = event["session_id"]
        _emit_event(node_id, event)

    stream.timed_out, stream.returncode = _process.stream_subprocess(
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
