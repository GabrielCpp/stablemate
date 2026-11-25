"""The ``OPENCODE_CONFIG_CONTENT`` an OpenCode turn runs under: agent permissions, confinement, extra directories and delegates."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from workhorse.runner.backends import AgentProfile, git_worktree, operator_config_dirs
from workhorse.runner.backends.delegates import Delegate

OPENCODE_VARIANT = {
    "low": "minimal",
    "medium": "",
    "high": "high",
    "xhigh": "max",
    "max": "max",
}

OPENCODE_OUTPUT_TOKEN_MAX_ENV = "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX"
OPENCODE_OUTPUT_TOKEN_MAX = "131072"

OPENCODE_CONFIG_ENV = "OPENCODE_CONFIG_CONTENT"

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


def _graft(base: dict[str, Any], extra: dict[str, Any]) -> dict[str, Any]:
    """``extra`` into ``base``: nested dicts recurse, lists join without repeats, and a scalar ``base`` set stays."""
    grafted = dict(base)
    for key, value in extra.items():
        current = grafted.get(key)
        if key not in grafted:
            grafted[key] = value
        elif isinstance(current, dict) and isinstance(value, dict):
            grafted[key] = _graft(current, value)
        elif isinstance(current, list) and isinstance(value, list):
            grafted[key] = [*current, *(item for item in value if item not in current)]
    return grafted


def _extra_dirs_config(add_dirs: list[str] | None) -> dict[str, Any]:
    """The skill folders and instruction files each extra directory holds, as the config keys that load them."""
    skills: list[str] = []
    instructions: list[str] = []
    for directory in add_dirs or []:
        root = Path(directory).resolve()
        skills += [
            str(root / folder) for folder in _SKILL_DIRS if (root / folder).is_dir()
        ]
        if (root / "AGENTS.md").is_file():
            instructions.append(str(root / "AGENTS.md"))
    config: dict[str, Any] = {}
    if skills:
        config["skills"] = {"paths": skills}
    if instructions:
        config["instructions"] = instructions
    return config


def _worktree(cwd: Path) -> Path:
    """The git worktree opencode resolves its path rules against."""
    worktree = git_worktree(cwd)
    if worktree is None:
        raise ValueError(
            f"a confined opencode turn needs a git worktree, and {cwd} is in none"
        )
    return worktree


def _under(worktree: Path, directory: Path) -> str:
    """The path rule matching everything under ``directory``, relative to ``worktree`` as opencode reads it.

    A directory holding the worktree gets the whole worktree, and ``external_directory``
    bounds the part of it above the worktree.
    """
    if worktree.is_relative_to(directory):
        return "**"
    return f"{directory.relative_to(worktree, walk_up=True).as_posix()}/**"


def _confinement(
    agent: AgentProfile, cwd: str | None, add_dirs: list[str] | None
) -> dict[str, Any]:
    """The tools and permission rules that hold a confined turn to its cwd, its added directories and its named commands.

    opencode matches a read or edit rule against the path relative to the git worktree,
    so an absolute pattern matches nothing and an added repo beside the worktree is
    ``../<repo>/**``. A path outside the worktree must also pass ``external_directory``,
    which opencode matches against the normalised absolute parent directory, so a ``..``
    cannot climb out of an added directory. The last matching rule wins, so each map
    opens with its deny. Its grep, glob and list tools answer outside
    those rules, so a confined turn does without them. The directories opencode loads
    project skills from and the operator's own config, skills and instructions from stay
    readable, and never writable.
    """
    here = Path(cwd or os.getcwd()).resolve()
    worktree = _worktree(here)
    added = [Path(directory).resolve() for directory in add_dirs or []]
    reachable = [here, *added]
    operator = list(operator_config_dirs("opencode"))
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
                for directory in [*added, *operator]
                if not directory.is_relative_to(worktree)
            },
        },
        "read": {
            "*": "deny",
            **{
                _under(worktree, directory): "allow"
                for directory in [*reachable, *operator]
            },
            **{f"{skills}/**": "allow" for skills in _SKILL_DIRS},
        },
        "edit": {
            "*": "deny",
            **{_under(worktree, directory): "allow" for directory in reachable},
        },
        "bash": {
            "*": "deny",
            **{
                rule: "allow"
                for command in agent.commands
                for rule in (command, f"{command} *")
            },
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
    variant = (
        OPENCODE_VARIANT.get(delegate.effort, delegate.effort)
        if delegate.effort
        else ""
    )
    if variant:
        entry["variant"] = variant
    if delegate.read_only:
        entry["permission"] = {"edit": "deny"}
    return entry


def config_content(
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
        overlay = _merge(
            overlay, {"agent": {d.name: _delegate_config(d) for d in delegates}}
        )
    extra = _extra_dirs_config(add_dirs)
    if not overlay and not extra:
        return operator
    return json.dumps(_merge(_graft(base, extra), overlay))
