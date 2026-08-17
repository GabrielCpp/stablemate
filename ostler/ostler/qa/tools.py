"""Unified QA tool registry: which external commands a repo has opted into, and what
they resolve to on this machine.

Two tiers, deliberately split by who owns the values:

- **Opt-in** — this repo's `agents.yml`/`.agents.yml`/`ostler.yml`/`ostler.yaml`'s
  `qa: {tools: [...]}` — is per-repo and lives in version control: which tools *this*
  QA plan may reach for.
- **Definition** — `~/.config/stablemate/config.toml`'s `[qa_tools.<name>]` — is
  per-machine: CI's `tesseract` is a container binary, a laptop's is Homebrew's, and a
  repo-committed path would be wrong on one of them the day it was written.

A name absent from the opt-in list is invisible to a plan even if the machine defines
it. A name present in the opt-in list but undefined anywhere ostler can see (and not
one of the built-ins) is a preflight error, not a silently empty catalog entry — the
same "blocked, not failed" doctrine `DriverBlocked` already applies to a missing
`maestro` CLI.

This module runs in ostler's own process, which is the only place `agents.yml` and the
stablemate config are reachable. The resolved `{name: command}` mapping crosses into
the harness subprocess through `PythonDriver._execute`'s `context` dict — see
`ostler.qa.harness.ostler_qa.Qa.tool`.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from ostler._vendor.stablemate_core.config import load_config
from ostler.qa.outcome import QaOutcome

#: Tools the harness ships a typed wrapper for (`qa.tesseract`, `qa.convert`). Their
#: command name needs no `[qa_tools.<name>]` entry unless a repo wants to override it —
#: e.g. pointing `convert` at `magick` on a machine where ImageMagick 7 dropped the alias.
BUILTIN_TOOLS: dict[str, str] = {
    "tesseract": "tesseract",
    "convert": "convert",
}

_QA_CONFIG_FILES = ("ostler.yml", "ostler.yaml", "agents.yml", ".agents.yml")


def _qa_block(root: Path) -> dict[str, Any]:
    """The first `qa:` mapping found across the repo's config files, in a fixed order.

    Reads the same four files `ostler.model._load_config` does, so a repo that keeps
    its `qa:` block in `agents.yml` is seen the same way one in `ostler.yml` is.
    """
    for name in _QA_CONFIG_FILES:
        path = root / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        qa = data.get("qa") if isinstance(data, dict) else None
        if isinstance(qa, dict):
            return qa
    return {}


def opted_in_tools(root: Path) -> set[str]:
    """The tool names this repo's `qa:` block lists under `tools:`."""
    values = _qa_block(root).get("tools", [])
    return {str(value) for value in values} if isinstance(values, list) else set()


@dataclass(frozen=True)
class ToolSpec:
    name: str
    command: str
    description: str
    builtin: bool

    @property
    def available(self) -> bool:
        return shutil.which(self.command) is not None


def _configured_tools(cfg: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    data = cfg if cfg is not None else load_config()
    table = data.get("qa_tools")
    if not isinstance(table, dict):
        return {}
    return {name: value for name, value in table.items() if isinstance(value, dict)}


def catalog(root: Path, *, cfg: dict[str, Any] | None = None) -> tuple[dict[str, ToolSpec], list[str]]:
    """Every opted-in tool, resolved to a `ToolSpec`, plus errors for names that resolve to nothing.

    A name resolves as: a `[qa_tools.<name>]` table if the machine config defines one
    (which lets it override a built-in's command), else a built-in, else neither — which
    is a config error, not an empty catalog entry.
    """
    configured = _configured_tools(cfg)
    specs: dict[str, ToolSpec] = {}
    errors: list[str] = []
    for name in sorted(opted_in_tools(root)):
        entry = configured.get(name)
        if entry is not None:
            command = entry.get("command")
            if not isinstance(command, str) or not command:
                errors.append(
                    f"qa tool {name!r} is opted into via agents.yml but its "
                    f"[qa_tools.{name}] table in the stablemate config has no `command`"
                )
                continue
            specs[name] = ToolSpec(
                name=name,
                command=command,
                description=str(entry.get("description", "")),
                builtin=name in BUILTIN_TOOLS,
            )
        elif name in BUILTIN_TOOLS:
            specs[name] = ToolSpec(
                name=name, command=BUILTIN_TOOLS[name], description=f"built-in {name} tool", builtin=True
            )
        else:
            errors.append(
                f"qa tool {name!r} is opted into via agents.yml's `qa: {{tools: [...]}}` "
                f"but is not a built-in and has no [qa_tools.{name}] table in "
                "~/.config/stablemate/config.toml"
            )
    return specs, errors


def cmd_catalog(root: Path, *, cfg: dict[str, Any] | None = None) -> QaOutcome:
    """The catalog as the rows the CLI prints and the coder workflow reads.

    `ok` is the predicate the CLI's exit code has always used: nothing failed to resolve
    *and* every resolved command is on PATH. An unreadable or malformed opt-in file is
    one more catalog error rather than a raise — a repo whose `agents.yml` cannot be
    parsed has no usable tools, which is what an error entry already says.
    """
    try:
        specs, errors = catalog(root, cfg=cfg)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        specs, errors = {}, [str(exc)]
    rows = [
        {
            "name": spec.name,
            "command": spec.command,
            "description": spec.description,
            "builtin": spec.builtin,
            "available": spec.available,
        }
        for spec in specs.values()
    ]
    missing = [str(row["name"]) for row in rows if not row["available"]]
    ok = not errors and not missing
    message = "\n".join(
        [*errors, *(f"qa tool {name!r} is not on PATH" for name in missing)]
    ) or f"{len(rows)} qa tool(s) available"
    return QaOutcome(ok=ok, message=message, data={"tools": rows, "errors": errors})


def preflight_errors(root: Path, *, cfg: dict[str, Any] | None = None) -> list[str]:
    """Every reason this repo's opted-in QA tools cannot run right now.

    Unresolved names (from `catalog`) and resolved-but-missing binaries alike — both are
    "this run cannot proceed", the distinction `DriverBlocked` already exists to carry.
    """
    specs, errors = catalog(root, cfg=cfg)
    missing = [
        f"qa tool {spec.name!r} names command {spec.command!r}, which is not on PATH"
        for spec in specs.values()
        if not spec.available
    ]
    return [*errors, *missing]


def resolved_commands(root: Path, *, cfg: dict[str, Any] | None = None) -> dict[str, str]:
    """`{name: command}` for every opted-in tool that resolved to a definition.

    Threaded into the harness subprocess's `context["tools"]` — the one channel across
    the process boundary — so `qa.tool(name)` and the typed wrappers see exactly the
    commands this repo opted into, nothing more that ostler's own process merely knows
    about.
    """
    specs, _errors = catalog(root, cfg=cfg)
    return {spec.name: spec.command for spec in specs.values()}
