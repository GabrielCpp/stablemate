"""Run a command under an environment page: its literals composed with the values saddlebag holds."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from ostler.environments.page import Variables, read_variables, slug_of
from ostler.environments.runtime import Runner, run_command
from ostler.model import UINode

_PLAIN_CHARS = frozenset(" #\"'")


class ResolutionError(RuntimeError):
    """A held name that saddlebag cannot supply from exactly one record."""


class ClassifyError(RuntimeError):
    """The secret classifier could not run or printed an answer that cannot be read."""


@dataclass(frozen=True)
class Resolved:
    """The page's literals and, for each held name, the saddlebag secret that holds it."""

    literals: Mapping[str, str]
    bindings: Mapping[str, str]


def records(slug: str, runner: Runner) -> list[tuple[str, str]]:
    outcome = runner(["saddlebag", "list", "--tag", f"environment={slug}", "--json"], capture=True)
    if outcome.returncode != 0:
        tail = "\n".join((outcome.stderr or "").strip().splitlines()[-5:])
        raise ResolutionError(
            f"saddlebag list exited {outcome.returncode}" + (f":\n{tail}" if tail else ""))
    try:
        listed = json.loads(outcome.stdout)["secrets"]
        return [(str(secret["name"]), str(secret["var"])) for secret in listed]
    except (ValueError, KeyError, TypeError) as exc:
        raise ResolutionError(f"saddlebag list printed an unreadable answer: {exc}") from exc


def resolve(node: UINode, runner: Runner) -> Resolved:
    """The page's variables, each held name bound to the one saddlebag record tagged for this page."""
    variables = read_variables(node)
    slug = slug_of(node)
    bindings: dict[str, str] = {}
    if variables.held:
        by_var: dict[str, list[str]] = {}
        for name, var in records(slug, runner):
            by_var.setdefault(var, []).append(name)
        for name in sorted(variables.held):
            names = by_var.get(name, [])
            if not names:
                raise ResolutionError(
                    f"the held mark {name} on {node.id} has no saddlebag record tagged "
                    f"environment={slug} with var {name}; register one with: "
                    f"saddlebag secret create <name> --var {name} --tag environment={slug}")
            if len(names) > 1:
                raise ResolutionError(
                    f"{name} on {node.id} is held by {len(names)} saddlebag records tagged "
                    f"environment={slug}: {' and '.join(sorted(names))}; keep one")
            bindings[name] = names[0]
    return Resolved(variables.literals, bindings)


def _verdicts(outcome: subprocess.CompletedProcess[str]) -> list[tuple[str, str | None]]:
    if outcome.returncode != 0:
        tail = "\n".join((outcome.stderr or "").strip().splitlines()[-5:])
        raise ClassifyError(
            f"saddlebag env classify exited {outcome.returncode}" + (f": {tail}" if tail else ""))
    try:
        verdicts = json.loads(outcome.stdout)["verdicts"]
        return [(str(v["key"]), str(v["rule"]) if v["secret"] else None) for v in verdicts]
    except (ValueError, KeyError, TypeError) as exc:
        raise ClassifyError(f"saddlebag env classify printed an unreadable answer: {exc}") from exc


def classify_literals(
    entries: list[tuple[str, str]], runner: Runner = run_command,
) -> dict[str, str | None]:
    """Each name's secret rule from `saddlebag env classify`, `None` for a value that reads as plain."""
    stdin = "".join(f"{name}={value}\n" for name, value in entries)
    try:
        outcome = runner(["saddlebag", "env", "classify", "-", "--json"], capture=True, stdin=stdin)
    except OSError as exc:
        raise ClassifyError(f"saddlebag could not run: {exc.strerror or exc}") from exc
    return dict(_verdicts(outcome))


def classify_file(path: Path, runner: Runner = run_command) -> list[tuple[str, str | None]]:
    """Each assignment of the dotenv *path* in file order, with its secret rule or `None`."""
    try:
        outcome = runner(["saddlebag", "env", "classify", str(path), "--json"], capture=True)
    except OSError as exc:
        raise ClassifyError(f"saddlebag could not run: {exc.strerror or exc}") from exc
    return _verdicts(outcome)


def exec_argv(resolved: Resolved, command: list[str]) -> list[str]:
    """The command wrapped in `saddlebag exec` for each binding, or *command* itself when there are none."""
    if not resolved.bindings:
        return list(command)
    flags = [part for var in sorted(resolved.bindings)
             for part in ("--env", f"{var}={resolved.bindings[var]}")]
    return ["saddlebag", "exec", *flags, "--", *command]


def composed_environment(resolved: Resolved, base: Mapping[str, str]) -> dict[str, str]:
    """The process environment with the page's literals over it."""
    return {**base, **resolved.literals}


def _dotenv_value(value: str) -> str:
    if not any(char in _PLAIN_CHARS for char in value):
        return value
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def render_dotenv(variables: Variables, source: str) -> str:
    """A dotenv of the page's variables in page order, the held names blank."""
    lines = [f"# rendered by ostler env dotenv from {source}; edit the page, not this file"]
    lines += [f"{name}=" if value is None else f"{name}={_dotenv_value(value)}"
              for name, value in variables.entries]
    return "\n".join(lines) + "\n"


def ensure_ignored(repo: Path, relative: str) -> bool:
    """Add *relative* to the repo's `.gitignore` unless a line already names it."""
    target = repo / ".gitignore"
    text = target.read_text(encoding="utf-8") if target.is_file() else ""
    present = {line.strip() for line in text.splitlines() if not line.lstrip().startswith("#")}
    if relative in present or f"/{relative}" in present:
        return False
    lead = "" if not text or text.endswith("\n") else "\n"
    target.write_text(f"{text}{lead}{relative}\n", encoding="utf-8")
    return True
