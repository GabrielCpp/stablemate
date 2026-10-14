"""Claude Code CLI (``claude -p``) — its ``stream-json`` / ``--resume`` / ``/compact`` protocol, and the adapter that exposes it as an ``AgentBackend``."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workhorse import otel, reload
from workhorse.config_run import AgentResilience
from workhorse.runner import acp
from workhorse.runner import failure as _failure
from workhorse.runner import process as _process
from workhorse.runner import usage as _usage
from workhorse.runner.backends import AgentBackend, AgentProfile, git_worktree
from workhorse.runner.backends.delegates import Delegate


_OUTLIVING_TOOLS = ("Workflow", "Monitor", "ScheduleWakeup", "CronCreate", "RemoteTrigger")
_FOREGROUND_ENV = {"CLAUDE_CODE_DISABLE_BACKGROUND_TASKS": "1"}
_READ_ONLY_TOOLS = ("Read", "Grep", "Glob", "Bash")


class ClaudeBackend(AgentBackend):
    """Claude Code CLI (``claude -p``)."""

    name = "claude"
    default_model = "sonnet"
    supports_compaction = True

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return ClaudeTranscript()

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
        delegates: tuple[Delegate, ...] = (),
    ) -> str:
        """Run one Claude CLI turn and return its final result text."""
        cmd = [
            "claude",
            *_permission_flags(agent),
            "--output-format", "stream-json",
            "--verbose",
            "--disallowedTools", *_OUTLIVING_TOOLS,
            *_tool_flags(agent, cwd),
        ]
        if model:
            cmd.extend(["--model", model])
        if effort:
            cmd.extend(["--effort", effort])
        if agent is not None and agent.steps is not None:
            cmd.extend(["--max-turns", str(agent.steps)])
        for directory in [*(add_dirs or []), *_skill_dirs(agent, cwd)]:
            cmd.extend(["--add-dir", directory])
        if delegates:
            cmd.extend(["--agents", _agents_json(delegates)])
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
            env_extra={**_FOREGROUND_ENV, **self.harness_env(), **_command_timeout_env(agent)},
            session_id_path=session_id_path,
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


def _agents_json(delegates: tuple[Delegate, ...]) -> str:
    """The ``--agents`` value that defines each delegate as a subagent for this session."""
    agents: dict[str, dict[str, object]] = {}
    for delegate in delegates:
        entry: dict[str, object] = {
            "description": delegate.description,
            "prompt": delegate.instructions,
            "model": delegate.model,
        }
        if delegate.effort:
            entry["effort"] = delegate.effort
        if delegate.read_only:
            entry["tools"] = list(_READ_ONLY_TOOLS)
        agents[delegate.name] = entry
    return json.dumps(agents)


def _permission_flags(agent: AgentProfile | None) -> list[str]:
    """Skip every permission prompt, or for a confined profile refuse whatever its rules do not allow.

    Under `dontAsk` the CLI allows reads inside the cwd and the added directories and
    denies every other call no rule allows. Only the project's settings are loaded, so
    an operator's own allow rules cannot widen the turn.
    """
    if agent is None or not agent.confined:
        return ["--dangerously-skip-permissions"]
    return ["--permission-mode", "dontAsk", "--setting-sources", "project"]


def _command_timeout_env(agent: AgentProfile | None) -> dict[str, str]:
    """The environment that lets one shell command run for the profile's limit, where the CLI would move it to the background after two minutes."""
    if agent is None or agent.command_timeout_s is None:
        return {}
    limit = str(agent.command_timeout_s * 1000)
    return {"BASH_DEFAULT_TIMEOUT_MS": limit, "BASH_MAX_TIMEOUT_MS": limit}


def _skill_dirs(agent: AgentProfile | None, cwd: str | None) -> list[str]:
    """The project skill directory a confined turn may read, since the skills it loads are files it opens."""
    if agent is None or not agent.confined:
        return []
    worktree = git_worktree(Path(cwd or os.getcwd()).resolve())
    if worktree is None:
        return []
    skills = worktree / _SKILL_DIR
    return [str(skills)] if skills.is_dir() else []


def _tool_flags(agent: AgentProfile | None, cwd: str | None) -> list[str]:
    """The flags that narrow a turn to its profile's tools: `--tools` and no MCP server when `*` is off, else a deny list."""
    tools = agent.tools if agent else {}
    named = {name: on for name, on in tools.items() if name != "*"}
    if agent is not None and agent.confined:
        shell = ["Bash"] if agent.commands else []
        enabled = dict.fromkeys([*_CONFINED_TOOLS, *shell, *(name for name, on in named.items() if on)])
        here = Path(cwd or os.getcwd()).resolve()
        allowed = [f"Edit(/{here}/**)", *(rule for command in agent.commands for rule in (f"Bash({command})", f"Bash({command} *)"))]
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
    session_id_path: Path | None = None,
) -> ClaudeTurnStream:
    """Run ``cmd`` through the shared supervised spawn path and parse Claude's stream-json, echoing a concise live view to stdout.

    The session id is written to ``session_id_path`` as soon as the stream names it, so a turn cut mid-stream resumes it.
    """
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
            _failure.record_session_start(session_id_path, stream.session_id)
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


_SUMMARY_KEYS = ("file_path", "path", "command", "pattern", "url", "query", "description")


def _tool_summary(inp: dict) -> str:
    return acp.summarize(inp, _SUMMARY_KEYS)


_TOOL_KINDS = {
    "Read": "read",
    "Edit": "edit",
    "MultiEdit": "edit",
    "Write": "edit",
    "NotebookEdit": "edit",
    "Bash": "execute",
    "Grep": "search",
    "Glob": "search",
    "WebFetch": "fetch",
    "WebSearch": "fetch",
}


def _tool_diffs(name: str, inp: dict[str, Any]) -> list[dict[str, Any]]:
    """The file changes a Claude edit tool's input spells out."""
    path = str(inp.get("file_path") or inp.get("notebook_path") or "")
    if name == "Edit" and "old_string" in inp and "new_string" in inp:
        return [acp.diff_item(path, inp["old_string"], inp["new_string"])]
    if name == "MultiEdit":
        return [
            acp.diff_item(path, edit["old_string"], edit["new_string"])
            for edit in inp.get("edits") or []
            if "old_string" in edit and "new_string" in edit
        ]
    if name == "Write" and "content" in inp:
        return [acp.diff_item(path, None, inp["content"])]
    return []


_TASK_TOOLS = ("TaskCreate", "TaskUpdate", "TaskList", "TaskGet")
_TASK_ID = re.compile(r"Task #(\w+)")


def _plan_status(status: object) -> str:
    if status in ("in_progress", "completed"):
        return str(status)
    return "pending"


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            str(b.get("text", "")) for b in content if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


class ClaudeTranscript(acp.TranscriptMapper):
    """Claude's stream-json events as ACP updates."""

    def __init__(self) -> None:
        super().__init__()
        self._plan_calls: set[str] = set()
        self._tasks: list[dict[str, str | None]] = []
        self._creating: dict[str, dict[str, str | None]] = {}
        self._diffs: dict[str, list[dict[str, Any]]] = {}

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        etype = event.get("type")
        if etype == "system":
            if event.get("session_id"):
                self.session_id = event["session_id"]
            return []
        if etype not in ("assistant", "user"):
            return []
        content = event.get("message", {}).get("content")
        if not isinstance(content, list):
            return []
        parent = event.get("parent_tool_use_id") or None
        mapped: list[acp.Update] = []
        for block in content:
            if etype == "assistant":
                mapped.extend(self._assistant_block(block))
            elif block.get("type") == "tool_result":
                if block.get("tool_use_id") in self._plan_calls:
                    self._task_result(block)
                else:
                    mapped.append(self._tool_result(block))
        return [acp.MappedUpdate(update, parent) for update in mapped]

    def _assistant_block(self, block: dict[str, Any]) -> list[acp.Update]:
        btype = block.get("type")
        if btype == "text" and block.get("text", "").strip():
            return [acp.agent_message_chunk(block["text"])]
        if btype == "thinking" and block.get("thinking", "").strip():
            return [acp.agent_thought_chunk(block["thinking"])]
        if btype == "tool_use":
            update = self._tool_use(block)
            return [update] if update else []
        return []

    def _tool_use(self, block: dict[str, Any]) -> acp.Update | None:
        name = block.get("name", "?")
        inp = block.get("input") or {}
        if name == "TodoWrite":
            self._plan_calls.add(block["id"])
            return acp.plan(
                [
                    acp.plan_entry(str(todo.get("content", "")), _plan_status(todo.get("status")))
                    for todo in inp.get("todos") or []
                ]
            )
        if name in _TASK_TOOLS:
            self._plan_calls.add(block["id"])
            return self._task_tool(block["id"], name, inp)
        kind = _TOOL_KINDS.get(name, "other")
        path = inp.get("file_path") or inp.get("notebook_path")
        diffs = _tool_diffs(name, inp)
        if diffs:
            self._diffs[block["id"]] = diffs
        return acp.tool_call(
            block["id"],
            f"{name} {_tool_summary(inp)}".rstrip(),
            kind,
            content=diffs,
            locations=[{"path": path}] if path and kind in ("read", "edit") else None,
            raw_input=inp,
        )

    def _task_plan(self) -> acp.Update:
        return acp.plan(
            [acp.plan_entry(task["subject"] or "", _plan_status(task["status"])) for task in self._tasks]
        )

    def _task_tool(self, call_id: str, name: str, inp: dict[str, Any]) -> acp.Update | None:
        if name == "TaskCreate":
            task: dict[str, str | None] = {"id": None, "subject": str(inp.get("subject", "")), "status": "pending"}
            self._tasks.append(task)
            self._creating[call_id] = task
            return self._task_plan()
        if name != "TaskUpdate":
            return None
        found = next((t for t in self._tasks if t["id"] == str(inp.get("taskId"))), None)
        if found is None:
            return None
        if inp.get("status") == "deleted":
            self._tasks.remove(found)
        else:
            if inp.get("subject"):
                found["subject"] = str(inp["subject"])
            if inp.get("status"):
                found["status"] = str(inp["status"])
        return self._task_plan()

    def _task_result(self, block: dict[str, Any]) -> None:
        task = self._creating.pop(block["tool_use_id"], None)
        found = _TASK_ID.search(_result_text(block.get("content")))
        if task is not None and found and not block.get("is_error"):
            task["id"] = found.group(1)

    def _tool_result(self, block: dict[str, Any]) -> acp.Update:
        text = _result_text(block.get("content"))
        content = self._diffs.pop(block["tool_use_id"], [])
        if text:
            content = [*content, acp.text_item(text)]
        return acp.tool_call_update(
            block["tool_use_id"],
            status="failed" if block.get("is_error") else "completed",
            content=content or None,
        )
