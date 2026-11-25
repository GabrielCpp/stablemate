"""OpenAI Codex CLI (``codex exec --json``) — its event vocabulary and its adapter."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Any

from workhorse.runner import acp
from workhorse.runner import usage as _usage
from workhorse.runner.usage import TurnUsage
from workhorse.runner.backends import AgentProfile, TurnRequest, git_worktree
from workhorse.runner.backends.guard import Policy, hook_command, policy_file
from workhorse.runner.backends.policy import confined_policy
from workhorse.runner.backends.delegates import Delegate
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import (
    TurnState,
    finalize_turn,
    read_session_id,
    recording,
)


def _parse_codex_model(model: str | None) -> tuple[str | None, str | None]:
    """Parse a node's ``model:`` string into ``(profile, model_slug)`` for codex."""
    raw = (model or "").strip()
    if not raw:
        return None, None
    if "@" in raw:
        prof, _, slug = raw.partition("@")
        return (prof.strip() or None), (slug.strip() or None)
    return raw, None


SKILL_DIRS = (".claude/skills", ".agents/skills")


def _skill_roots(cwd: Path) -> list[Path]:
    worktree = git_worktree(cwd)
    return [worktree / name for name in SKILL_DIRS if (worktree / name).is_dir()] if worktree else []


def guard_policy(agent: AgentProfile | None, cwd: str | None, add_dirs: list[str] | None) -> Policy | None:
    return confined_policy(agent, cwd, add_dirs, "codex", _skill_roots)


def guard_flags(policy_path: Path) -> list[str]:
    """The flags that run the guard before every tool call of the turn."""
    command = json.dumps(hook_command(policy_path))
    hooks = f'hooks.PreToolUse=[{{matcher=".*",hooks=[{{type="command",command={command}}}]}}]'
    return ["--dangerously-bypass-hook-trust", "-c", hooks]


@contextmanager
def flags_with_policy_file(policy: Policy | None) -> Iterator[list[str]]:
    """The guard's flags for a turn held to `policy`, with the policy in a file that lasts as long as the turn. No flags when there is no policy."""
    if policy is None:
        yield []
        return
    with policy_file(policy) as path:
        yield guard_flags(path)


def _role_toml(delegate: Delegate) -> str:
    """A codex agent role's config layer: the delegate's model, effort, sandbox and instructions."""
    _, slug = _parse_codex_model(delegate.model)
    lines = [f"model = {json.dumps(slug or delegate.model)}"]
    if delegate.effort:
        lines.append(f"model_reasoning_effort = {json.dumps(delegate.effort)}")
    if delegate.read_only:
        lines.append('sandbox_mode = "read-only"')
    lines.append(f"developer_instructions = {json.dumps(delegate.instructions)}")
    return "\n".join(lines) + "\n"


@contextmanager
def flags_with_role_files(delegates: tuple[Delegate, ...]) -> Iterator[list[str]]:
    """The ``-c agents.*`` flags that define each delegate as a codex agent role, with its role file lasting as long as the turn."""
    if not delegates:
        yield []
        return
    with tempfile.TemporaryDirectory(prefix="codex-roles-") as directory:
        flags: list[str] = []
        for delegate in delegates:
            role_file = Path(directory) / f"{delegate.name}.toml"
            _ = role_file.write_text(_role_toml(delegate), encoding="utf-8")
            flags += [
                "-c", f"agents.{delegate.name}.description={json.dumps(delegate.description)}",
                "-c", f"agents.{delegate.name}.config_file={json.dumps(str(role_file))}",
            ]
        yield flags


_CUMULATIVE_FIELDS = ("input_tokens", "cache_read_input_tokens", "output_tokens", "reasoning_output_tokens")


def _cumulative_path(session_id_path: Path | None) -> Path | None:
    return session_id_path.with_name(session_id_path.name + ".usage.json") if session_id_path else None


def _read_cumulative(path: Path | None, session_id: str | None) -> dict[str, int]:
    if path is None or session_id is None or not path.exists():
        return {}
    try:
        stored = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(stored, dict) or stored.get("session_id") != session_id:
        return {}
    return {name: stored[name] for name in _CUMULATIVE_FIELDS if isinstance(stored.get(name), int)}


def per_turn_usage(usage: TurnUsage, session_id: str | None, session_id_path: Path | None, resumed: bool) -> TurnUsage:
    """What this turn alone consumed, with input counting only the uncached tokens.

    Codex reports session-cumulative counts whose input includes the cached input, so a resumed session's earlier turns are subtracted first.
    """
    if usage.is_empty:
        return usage
    path = _cumulative_path(session_id_path)
    before = _read_cumulative(path, session_id) if resumed else {}
    cumulative = {name: getattr(usage, name) for name in _CUMULATIVE_FIELDS}
    if path is not None and session_id:
        stored = {name: count for name, count in cumulative.items() if count is not None}
        try:
            _ = path.write_text(json.dumps({"session_id": session_id, **stored}), encoding="utf-8")
        except OSError:
            pass
    delta = {
        name: None if count is None else max(count - before.get(name, 0), 0)
        for name, count in cumulative.items()
    }
    cached = delta["cache_read_input_tokens"]
    fresh = delta["input_tokens"]
    if fresh is not None:
        fresh = max(fresh - (cached or 0), 0)
    return replace(usage, **{**delta, "input_tokens": fresh})


NON_FAILURE_MARKERS = ("apply_patch verification failed", "blocked by PreToolUse hook", "`--dangerously-bypass-hook-trust` is enabled")


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
            if not any(marker in str(item.get("message") or "") for marker in NON_FAILURE_MARKERS):
                state.diagnostics.append(str(item)[:500])
    elif "error" in etype or "fail" in etype:
        state.diagnostics.append(json.dumps(event)[:500])


_TOOL_ITEMS = ("command_execution", "file_change", "mcp_tool_call", "web_search")


def _output_items(text: str) -> list[dict[str, Any]]:
    return [acp.text_item(text)] if text else []


class CodexTranscript(acp.TranscriptMapper):
    """Codex's ``exec --json`` items as ACP updates."""

    def __init__(self) -> None:
        super().__init__()
        self._open: set[str] = set()

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        etype = event.get("type")
        if etype == "thread.started":
            self.session_id = event.get("thread_id") or self.session_id
            return []
        if etype not in ("item.started", "item.updated", "item.completed"):
            return []
        item = event.get("item") or {}
        kind = item.get("type")
        done = etype == "item.completed"
        if kind == "todo_list":
            return [acp.MappedUpdate(self._plan(item))]
        if kind in _TOOL_ITEMS:
            return [acp.MappedUpdate(update) for update in self._tool(item, done)]
        if done and item.get("text"):
            if kind == "agent_message":
                return [acp.MappedUpdate(acp.agent_message_chunk(item["text"]))]
            if kind == "reasoning":
                return [acp.MappedUpdate(acp.agent_thought_chunk(item["text"]))]
        return []

    def _plan(self, item: dict[str, Any]) -> acp.Update:
        return acp.plan(
            [
                acp.plan_entry(str(todo.get("text", "")), "completed" if todo.get("completed") else "pending")
                for todo in item.get("items") or []
            ]
        )

    def _tool(self, item: dict[str, Any], done: bool) -> list[acp.Update]:
        call_id = str(item.get("id", ""))
        if call_id not in self._open:
            if not done:
                self._open.add(call_id)
                return [self._call(item)]
            call = self._call(item)
            status, content = self._outcome(item)
            call["status"] = status
            if content:
                call["content"] = content
            return [call]
        if not done:
            return []
        self._open.discard(call_id)
        status, content = self._outcome(item)
        return [acp.tool_call_update(call_id, status=status, content=content or None)]

    def _call(self, item: dict[str, Any]) -> acp.Update:
        call_id = str(item.get("id", ""))
        kind = item.get("type")
        if kind == "command_execution":
            command = str(item.get("command", ""))
            return acp.tool_call(call_id, command, "execute", raw_input={"command": command})
        if kind == "file_change":
            paths = [str(change.get("path", "")) for change in item.get("changes") or []]
            return acp.tool_call(
                call_id,
                " ".join(["Edit", *paths]),
                "edit",
                locations=[{"path": path} for path in paths],
            )
        if kind == "mcp_tool_call":
            return acp.tool_call(
                call_id,
                f"{item.get('server', '?')}.{item.get('tool', '?')}",
                "other",
                raw_input=item.get("arguments"),
            )
        return acp.tool_call(call_id, "Web search", "fetch")

    def _outcome(self, item: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        kind = item.get("type")
        failed = item.get("status") == "failed"
        if kind == "command_execution":
            failed = failed or item.get("exit_code") not in (None, 0)
            text = str(item.get("aggregated_output") or "")
        elif kind == "mcp_tool_call":
            error = item.get("error") or {}
            failed = failed or bool(error)
            blocks = (item.get("result") or {}).get("content") or []
            text = str(error.get("message") or "") or "\n".join(
                str(b.get("text", "")) for b in blocks if isinstance(b, dict) and b.get("type") == "text"
            )
        elif kind == "web_search":
            text = str(item.get("query") or "")
        else:
            text = ""
        return ("failed" if failed else "completed"), _output_items(text)


class CodexBackend(JsonlBackend):
    """OpenAI Codex CLI (``codex exec --json``)."""

    name = "codex"
    default_model = None

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return CodexTranscript()

    def execute(self, turn: TurnRequest) -> str:
        sid = read_session_id(turn.session_id_path)
        profile, model_slug = _parse_codex_model(turn.model)
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
        if turn.effort:
            flags += ["-c", f'model_reasoning_effort="{turn.effort}"']
        with (
            flags_with_policy_file(guard_policy(turn.agent, turn.cwd, turn.add_dirs)) as hook_flags,
            flags_with_role_files(turn.delegates) as role_flags,
        ):
            if sid:
                cmd = [*head, "exec", "resume", *flags, *hook_flags, *role_flags, sid, "-"]
                print(f"[{turn.node_id}] 🔄 Resuming codex session: {sid[:8]}...", flush=True)
            else:
                cmd = [*head, "exec", *flags, *hook_flags, *role_flags, "-"]
            state = self.stream(
                cmd, turn.node_id, turn.timeout, turn.prompt, recording(_on_event, turn.session_id_path),
                resilience=turn.resilience, cwd=turn.cwd,
                env_extra=self.harness_env(), non_failure_markers=NON_FAILURE_MARKERS,
            )
        state.usage = per_turn_usage(state.usage, state.session_id or sid, turn.session_id_path, sid is not None)
        return finalize_turn("codex", turn.node_id, state, turn.session_id_path, turn.timeout)
