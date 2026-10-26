"""OpenCode CLI (``opencode run --format json``) — event vocabulary, adapter, and the out-of-band probe for the ChatGPT/Codex provider's usage-window reset."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from workhorse.config_run import AgentResilience
from workhorse.runner import acp
from workhorse.runner import failure as _failure
from workhorse.runner import usage as _usage
from workhorse.runner.backends import (
    AgentProfile,
    ensure_prompt_is_not_in_argv,
    git_worktree,
    prepare_argv_prompt,
)
from workhorse.runner.backends.delegates import Delegate
from workhorse.runner.backends.jsonl import JsonlBackend
from workhorse.runner.backends.turn import (
    TurnState,
    finalize_turn,
    read_session_id,
    recording,
)
from workhorse.runner.usage import TurnUsage


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
            state.usage = state.usage.merge(_usage.normalize(event)).merge(
                TurnUsage(steps=1)
            )
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


_TOOL_KINDS = {
    "read": "read",
    "edit": "edit",
    "write": "edit",
    "patch": "edit",
    "apply_patch": "edit",
    "bash": "execute",
    "grep": "search",
    "glob": "search",
    "list": "search",
    "webfetch": "fetch",
    "websearch": "fetch",
}
_SUMMARY_KEYS = ("filePath", "path", "command", "pattern", "url", "query", "description")
_PRIORITIES = ("high", "medium", "low")


def _diffs(tool: str, inp: dict[str, Any]) -> list[dict[str, Any]]:
    """The file change an OpenCode edit tool's input spells out."""
    path = str(inp.get("filePath") or "")
    if tool == "edit" and "oldString" in inp and "newString" in inp:
        return [acp.diff_item(path, inp["oldString"], inp["newString"])]
    if tool == "write" and "content" in inp:
        return [acp.diff_item(path, None, inp["content"])]
    return []


class OpenCodeTranscript(acp.TranscriptMapper):
    """OpenCode's ``run --format json`` events as ACP updates.

    A ``tool_use`` event arrives once its tool has finished, so it yields the call and its result together.
    """

    def __init__(self) -> None:
        super().__init__()
        self._seen: dict[str, str] = {}

    def updates(self, event: dict[str, Any]) -> list[acp.MappedUpdate]:
        self.session_id = event.get("sessionID") or self.session_id
        part = event.get("part") or {}
        etype = event.get("type")
        if etype in ("text", "reasoning"):
            return [acp.MappedUpdate(u) for u in self._words(etype, part)]
        if etype == "tool_use":
            return [acp.MappedUpdate(u) for u in self._tool(part)]
        return []

    def _words(self, etype: str, part: dict[str, Any]) -> list[acp.Update]:
        text = str(part.get("text") or "")
        key = str(part.get("id") or "")
        before = self._seen.get(key, "") if key else ""
        if key:
            self._seen[key] = text
        fresh = text[len(before):] if text.startswith(before) else text
        if not fresh.strip():
            return []
        chunk = acp.agent_message_chunk if etype == "text" else acp.agent_thought_chunk
        return [chunk(fresh)]

    def _tool(self, part: dict[str, Any]) -> list[acp.Update]:
        tool = str(part.get("tool", "?"))
        state = part.get("state") or {}
        inp = state.get("input") or {}
        if tool == "todowrite":
            return [
                acp.plan(
                    [
                        acp.plan_entry(
                            str(todo.get("content", "")),
                            todo["status"] if todo.get("status") in ("in_progress", "completed") else "pending",
                            todo["priority"] if todo.get("priority") in _PRIORITIES else "medium",
                        )
                        for todo in inp.get("todos") or []
                    ]
                )
            ]
        call_id = str(part.get("callID", ""))
        kind = _TOOL_KINDS.get(tool, "other")
        path = inp.get("filePath")
        diffs = _diffs(tool, inp)
        call = acp.tool_call(
            call_id,
            f"{tool} {acp.summarize(inp, _SUMMARY_KEYS)}".rstrip(),
            kind,
            content=diffs,
            locations=[{"path": path}] if path and kind in ("read", "edit") else None,
            raw_input=inp,
        )
        status = state.get("status")
        if status not in ("completed", "error"):
            return [call]
        failed = status == "error" or state.get("metadata", {}).get("exit") not in (None, 0)
        text = str(state.get("error") if status == "error" else state.get("output") or "")
        content = [*diffs, acp.text_item(text)] if text else diffs
        return [call, acp.tool_call_update(call_id, status="failed" if failed else "completed", content=content or None)]


_OPENCODE_VARIANT = {"low": "minimal", "medium": "", "high": "high", "xhigh": "max", "max": "max"}

_OPENCODE_OUTPUT_TOKEN_MAX_ENV = "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"
_OPENCODE_OUTPUT_TOKEN_MAX = "131072"

_OPENCODE_CONFIG_ENV = "OPENCODE_CONFIG_CONTENT"

_OPENCODE_EDIT_ALIASES = frozenset({"write", "edit", "patch"})


def _merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """``overlay`` over ``base``, recursing into nested dicts so a key the operator set survives a sibling key we add."""
    merged = dict(base)
    for key, value in overlay.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge(current, value)
        else:
            merged[key] = value
    return merged


_SKILL_DIRS = (".opencode/skills", ".claude/skills", ".agents/skills")


def _worktree(cwd: Path) -> Path:
    """The git worktree opencode resolves its path rules against."""
    worktree = git_worktree(cwd)
    if worktree is None:
        raise ValueError(f"a confined opencode turn needs a git worktree, and {cwd} is in none")
    return worktree


def _under(worktree: Path, directory: Path) -> str:
    """The path rule matching everything under ``directory``, relative to ``worktree`` as opencode reads it.

    A directory holding the worktree gets the whole worktree, and ``external_directory``
    bounds the part of it above the worktree.
    """
    if worktree.is_relative_to(directory):
        return "**"
    return f"{directory.relative_to(worktree, walk_up=True).as_posix()}/**"


def _confinement(agent: AgentProfile, cwd: str | None, add_dirs: list[str] | None) -> dict[str, Any]:
    """The tools and permission rules that hold a confined turn to its cwd, its added directories and its named commands.

    opencode matches a read or edit rule against the path relative to the git worktree,
    so an absolute pattern matches nothing and an added repo beside the worktree is
    ``../<repo>/**``. A path outside the worktree must also pass ``external_directory``,
    which opencode matches against the normalised absolute parent directory, so a ``..``
    cannot climb out of an added directory. The last matching rule wins, so each map
    opens with its deny. Its grep, glob and list tools answer outside
    those rules, so a confined turn does without them. The directories opencode loads
    project skills from stay readable.
    """
    here = Path(cwd or os.getcwd()).resolve()
    worktree = _worktree(here)
    added = [Path(directory).resolve() for directory in add_dirs or []]
    reachable = [here, *added]
    tools = {
        **{name: on for name, on in agent.tools.items() if on},
        "*": False,
        "read": True,
        "edit": True,
        "write": True,
        "bash": bool(agent.commands),
        "grep": False,
        "glob": False,
        "list": False,
    }
    permission = {
        "external_directory": {
            "*": "deny",
            **{
                f"{directory.as_posix()}/**": "allow"
                for directory in added
                if not directory.is_relative_to(worktree)
            },
        },
        "read": {
            "*": "deny",
            **{_under(worktree, directory): "allow" for directory in reachable},
            **{f"{skills}/**": "allow" for skills in _SKILL_DIRS},
        },
        "edit": {"*": "deny", **{_under(worktree, directory): "allow" for directory in reachable}},
        "bash": {
            "*": "deny",
            **{rule: "allow" for command in agent.commands for rule in (command, f"{command} *")},
        },
    }
    return {"tools": tools, "permission": permission}


def _agent_config(
    agent: AgentProfile, cwd: str | None = None, add_dirs: list[str] | None = None
) -> dict[str, Any]:
    """``agent`` as the slice of opencode config that defines it.

    opencode folds an agent's ``tools`` map into its permission ruleset as a
    ``pattern: "*"`` rule, and a tool denied at that pattern has its JSON schema
    dropped from the request rather than merely refused. That is the point: the schema
    is otherwise resent on every step of the turn. Three names alias onto one ``edit``
    permission there, so ``write``, ``edit`` and ``patch`` cannot be separated, and
    denying any of them denies all three.
    """
    denied_aliases = sorted(
        name
        for name, allowed in agent.tools.items()
        if not allowed and name in _OPENCODE_EDIT_ALIASES
    )
    if denied_aliases:
        raise ValueError(
            f"opencode agent '{agent.name}' denies {', '.join(denied_aliases)}, which "
            "opencode aliases onto the single 'edit' permission, so that also removes "
            "the turn's other editing tools"
        )
    entry: dict[str, Any] = {}
    if agent.tools:
        entry["tools"] = dict(agent.tools)
    if agent.confined:
        entry.update(_confinement(agent, cwd, add_dirs))
    if agent.steps is not None:
        entry["steps"] = agent.steps
    config: dict[str, Any] = {"agent": {agent.name: entry}}
    if agent.disable_mcp:
        config["mcp"] = {server: {"enabled": False} for server in agent.disable_mcp}
    tool_output = {
        key: value
        for key, value in (
            ("max_lines", agent.tool_output_max_lines),
            ("max_bytes", agent.tool_output_max_bytes),
        )
        if value is not None
    }
    if tool_output:
        config["tool_output"] = tool_output
    return config


def _delegate_config(delegate: Delegate) -> dict[str, Any]:
    """One delegate as an opencode subagent entry."""
    entry: dict[str, Any] = {
        "mode": "subagent",
        "model": delegate.model,
        "description": delegate.description,
        "prompt": delegate.instructions,
    }
    variant = _OPENCODE_VARIANT.get(delegate.effort, delegate.effort) if delegate.effort else ""
    if variant:
        entry["variant"] = variant
    if delegate.read_only:
        entry["permission"] = {"edit": "deny"}
    return entry


def _config_content(
    operator: str | None,
    model: str | None,
    agent: AgentProfile | None,
    cwd: str | None = None,
    add_dirs: list[str] | None = None,
    delegates: tuple[Delegate, ...] = (),
) -> str | None:
    """The ``OPENCODE_CONFIG_CONTENT`` for this turn, merged over whatever the operator configured.

    opencode reads this variable as a final local-scope merge, so it is the one place
    that can both keep an operator's settings and add a per-node agent. The previous
    code skipped itself entirely whenever the operator had set the variable, which on
    any machine with a ``[harness.opencode].env`` entry meant ``small_model`` was never
    injected at all.
    """
    try:
        base = json.loads(operator) if operator else {}
    except json.JSONDecodeError:
        base = {}
    if not isinstance(base, dict):
        base = {}
    overlay: dict[str, Any] = {}
    if model and "small_model" not in base:
        overlay["small_model"] = model
    if agent is not None:
        overlay = _merge(overlay, _agent_config(agent, cwd, add_dirs))
    if delegates:
        overlay = _merge(overlay, {"agent": {d.name: _delegate_config(d) for d in delegates}})
    if not overlay:
        return operator
    return json.dumps(_merge(base, overlay))


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
    supports_subagents = True

    def transcript_mapper(self) -> acp.TranscriptMapper:
        return OpenCodeTranscript()

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
            "--auto",
        ]
        if model:
            cmd += ["-m", model]
        variant = _OPENCODE_VARIANT.get(effort, effort) if effort else ""
        if variant:
            cmd += ["--variant", variant]
        if sid:
            cmd += ["--session", sid]
            print(f"[{node_id}] 🔄 Resuming opencode session: {sid[:8]}...", flush=True)
        if agent is not None:
            cmd += ["--agent", agent.name]
        if attachment is not None:
            cmd += ["--file", str(attachment)]
        cmd += ["--", argv_prompt]
        ensure_prompt_is_not_in_argv(prompt, cmd)
        env_extra = self.harness_env()
        config = _config_content(
            env_extra.get(_OPENCODE_CONFIG_ENV), model, agent, cwd, add_dirs, delegates
        )
        if config is not None:
            env_extra = {**env_extra, _OPENCODE_CONFIG_ENV: config}
        if _OPENCODE_OUTPUT_TOKEN_MAX_ENV not in env_extra:
            env_extra = {
                _OPENCODE_OUTPUT_TOKEN_MAX_ENV: _OPENCODE_OUTPUT_TOKEN_MAX,
                **env_extra,
            }
        state = self.stream(
            cmd, node_id, timeout, None,
            recording(_OpenCodeEvents().on_event, session_id_path),
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
