"""Where a copy's `${VAR}` values come from: one source per repo, read as dotenv."""

from __future__ import annotations

import json
import os
import re
import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from ostler.environments import runtime
from ostler.environments.render import Copy, Rendered
from ostler.environments.runtime import Runner
from ostler.environments.spec import Catalog, Service, closure

ENV_FILE = "stack.env"
_ASSIGNMENT = re.compile(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_REFERENCE = re.compile(
    r"\$(?:\{([A-Za-z_][A-Za-z0-9_]*)(:?[-?+=][^}]*)?\}|([A-Za-z_][A-Za-z0-9_]*))")


class SecretError(RuntimeError):
    """A secret source that cannot supply its file or its names."""


class SecretSource(Protocol):
    """Supplies a copy's secret values as dotenv files, and the names those files define."""

    def names(self) -> frozenset[str]: ...

    def files(self, copy: Copy) -> list[Path]: ...

    def exec_prefix(self) -> list[str]: ...


class NoSecrets:
    """The source of a repo that names none: no names and no files."""

    def names(self) -> frozenset[str]:
        return frozenset()

    def files(self, copy: Copy) -> list[Path]:
        return []

    def exec_prefix(self) -> list[str]:
        return []


class DotenvFile:
    """A dotenv file in the checkout, read in place, or in the main checkout from a worktree."""

    def __init__(self, repo: Path, file: str) -> None:
        self._repo = repo
        self._file = file

    def _path(self) -> Path:
        path = self._repo / self._file
        main = runtime.main_checkout(self._repo)
        if not path.is_file() and main != self._repo and (main / self._file).is_file():
            return main / self._file
        return path

    def names(self) -> frozenset[str]:
        path = self._path()
        if not path.is_file():
            raise SecretError(f"the secret file {path} does not exist")
        return parse_names(path.read_text(encoding="utf-8"))

    def files(self, copy: Copy) -> list[Path]:
        path = self._path()
        if not path.is_file():
            raise SecretError(f"the secret file {path} does not exist")
        return [path]

    def exec_prefix(self) -> list[str]:
        return []


class DecryptCommand:
    """A shell command, run from the repo root, whose stdout is dotenv."""

    def __init__(self, repo: Path, command: str, runner: Runner) -> None:
        self._repo = repo
        self._command = command
        self._runner = runner
        self._output: str | None = None

    def _read(self) -> str:
        if self._output is None:
            script = f"cd {shlex.quote(str(self._repo))} && {self._command}"
            outcome = self._runner(["sh", "-c", script], capture=True)
            if outcome.returncode != 0:
                tail = "\n".join((outcome.stderr or "").strip().splitlines()[-5:])
                raise SecretError(
                    f"the decrypt command exited {outcome.returncode}"
                    + (f":\n{tail}" if tail else ""))
            self._output = outcome.stdout
        return self._output

    def names(self) -> frozenset[str]:
        return parse_names(self._read())

    def files(self, copy: Copy) -> list[Path]:
        text = self._read()
        target = copy.directory / runtime.SECRETS_DIR / ENV_FILE
        write_private(target, text)
        return [target]

    def exec_prefix(self) -> list[str]:
        return []


class SaddlebagSource:
    """The secrets saddlebag holds under some tags, which wraps every compose command."""

    def __init__(self, runner: Runner, query: list[str]) -> None:
        self._runner = runner
        self._tags = [part for pair in query for part in ("--tag", pair)]
        self._names: frozenset[str] | None = None

    def names(self) -> frozenset[str]:
        if self._names is None:
            outcome = self._runner(["saddlebag", "list", *self._tags, "--json"], capture=True)
            if outcome.returncode != 0:
                tail = "\n".join((outcome.stderr or "").strip().splitlines()[-5:])
                raise SecretError(
                    f"saddlebag list exited {outcome.returncode}" + (f":\n{tail}" if tail else ""))
            self._names = self._parse(outcome.stdout)
        return self._names

    @staticmethod
    def _parse(text: str) -> frozenset[str]:
        try:
            listed = json.loads(text)["secrets"]
            found: set[str] = set()
            for secret in listed:
                if not secret["var"]:
                    raise SecretError(
                        f"the saddlebag secret `{secret['name']}` has no environment variable")
                found.add(str(secret["var"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise SecretError(f"saddlebag list printed an unreadable answer: {exc}") from exc
        return frozenset(found)

    def files(self, copy: Copy) -> list[Path]:
        return []

    def exec_prefix(self) -> list[str]:
        return ["saddlebag", "exec", *self._tags, "--"]


def write_private(path: Path, text: str) -> None:
    """Write *text* to *path*, a file created readable by its owner alone."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(text)


def source_for(catalog: Catalog, repo: Path, runner: Runner) -> SecretSource:
    """The secret source the stack root names, or the null one."""
    if catalog.secrets.file:
        return DotenvFile(repo, catalog.secrets.file)
    if catalog.secrets.decrypt:
        return DecryptCommand(repo, catalog.secrets.decrypt, runner)
    if catalog.secrets.saddlebag:
        return SaddlebagSource(runner, catalog.secrets.saddlebag.split())
    return NoSecrets()


def parse_names(text: str) -> frozenset[str]:
    """The names a dotenv text defines, read without keeping any value."""
    found: set[str] = set()
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        match = _ASSIGNMENT.match(line)
        if match:
            found.add(match.group(1))
    return frozenset(found)


def required_names(text: str) -> frozenset[str]:
    """The `$NAME`, `${NAME}` and `${NAME:?msg}` references in *text* that have no default."""
    required: set[str] = set()
    for match in _REFERENCE.finditer(text.replace("$$", "")):
        operator = match.group(2) or ""
        if match.group(3):
            required.add(match.group(3))
        elif not operator or operator.lstrip(":").startswith("?"):
            required.add(match.group(1))
    return frozenset(required)


def allowed_names(source: SecretSource, catalog: Catalog, service: Service) -> frozenset[str]:
    """The names a rendered block of *service* may reference: the source's and its jobs' outputs."""
    produced = {name for need in closure(catalog, [service.ref]) if need.ref != service.ref
                for name in need.outputs}
    return source.names() | produced


def missing_names(
    rendered: Rendered, catalog: Catalog, services: Iterable[Service], source: SecretSource,
) -> list[str]:
    """One line per name a rendered block requires that its allowed set does not define."""
    lines: list[str] = []
    for service in services:
        absent = (required_names(rendered.defines.get(service.ref, ""))
                  - allowed_names(source, catalog, service))
        lines += [f"`{name}` is required by {service.ref}" for name in sorted(absent)]
    return lines
