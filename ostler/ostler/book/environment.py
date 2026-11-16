"""A place a service runs: the hosts that reach it, the saddlebag secrets its
cast signs in with, and the backstage that can arrange state there. The book
holds secret names only. A value reaches the process through the environment
variable `BOOK_SECRET_<HANDLE>`, which saddlebag fills."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

from ostler.book.errors import BookError
from ostler.environments import commands, runtime
from ostler.environments.render import COMPOSE_FILE, SHARED, Copy
from ostler.environments.runtime import Runner, run_command
from ostler.qa.addresses import LEASE_ENV

if TYPE_CHECKING:
    from ostler.book.delivery import Delivery

OSTLER = "ostler:"
PREFIX = "BOOK_SECRET_"
GUARD = "BOOK_REEXEC"
GONE = "No such container"


@dataclass
class Environment:
    name: str
    hosts: dict[str, str]
    secrets: dict[str, str] = field(default_factory=dict)
    backstage: type | None = None
    root: str = ""
    leased: str = ""
    delivery: Delivery | None = None
    runner: Runner = field(default=run_command, repr=False, compare=False)
    _roots: dict[str, Path] = field(default_factory=dict, init=False, repr=False, compare=False)
    _books: dict[str, tuple[int, dict[str, str]]] = field(default_factory=dict, init=False, repr=False, compare=False)
    _answers: dict[tuple[str, str], str] = field(default_factory=dict, init=False, repr=False, compare=False)
    _containers: dict[tuple[str, str], str] = field(default_factory=dict, init=False, repr=False, compare=False)

    def address(self, host: str) -> str:
        if host not in self.hosts:
            raise BookError(f"environment {self.name!r} knows no host called {host!r}")
        url = self.hosts[host]
        if not url.startswith(OSTLER):
            return url
        copy = runtime.copy_for(self._stack_root(), self._copy_of(url))
        book_file = copy.directory / runtime.ADDRESSES
        try:
            stamp = book_file.stat().st_mtime_ns
        except OSError:
            stamp = -1
        known = self._books.get(copy.name)
        if known is None or known[0] != stamp:
            known = (stamp, commands.read_book(copy))
            self._books[copy.name] = known
            self._answers = {key: value for key, value in self._answers.items() if key[0] != copy.name}
        kept = self._answers.get((copy.name, host))
        if kept is not None:
            return kept
        outcome = commands.lookup(copy, known[1], host)
        if not outcome.ok:
            raise RuntimeError(outcome.message + "\n")
        self._answers[(copy.name, host)] = outcome.message
        return outcome.message

    def exec(self, service: str, argv: Sequence[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Runs *argv* in the running container of *service* of this environment's copy."""
        copy = self._rendered_copy()
        done = self._exec_once(copy, service, argv, stdin)
        if done.returncode and GONE in (done.stderr or ""):
            self._containers.pop((copy.name, service), None)
            done = self._exec_once(copy, service, argv, stdin)
        return done

    def _exec_once(self, copy: Copy, service: str, argv: Sequence[str], stdin: str | None) -> subprocess.CompletedProcess[str]:
        key = (copy.name, service)
        if key not in self._containers:
            self._containers[key] = self._container(copy, service)
        command = ["docker", "exec", *(["-i"] if stdin is not None else []), self._containers[key], *argv]
        return self.runner(command, capture=True, stdin=stdin)

    def compose(self, args: Sequence[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
        """Runs `docker compose` with *args* against this environment's copy, as `run --rm` one-shots need."""
        copy = self._rendered_copy()
        return self.runner(runtime.Compose(copy).argv(args), capture=True, stdin=stdin)

    def _container(self, copy: Copy, service: str) -> str:
        done = runtime.Compose(copy, self.runner).run(["ps", "-q", service], capture=True)
        lines = done.stdout.split() if done.returncode == 0 else []
        if not lines:
            raise RuntimeError(f"{copy.name} runs no container for `{service}`" + (f": {done.stderr.strip()}" if done.stderr else ""))
        return lines[0]

    def _rendered_copy(self) -> Copy:
        name = self.copy()
        if not name:
            raise BookError(f"environment {self.name!r} reaches no stack copy")
        copy = runtime.copy_for(self._stack_root(), name)
        if not (copy.directory / COMPOSE_FILE).is_file():
            raise RuntimeError(f"{copy.name} has not been rendered: run `ostler env up` first")
        return copy

    def _stack_root(self) -> Path:
        start = self.root or str(Path.cwd())
        if start not in self._roots:
            self._roots[start] = commands.env_root(Path(start))
        return self._roots[start]

    def copy(self) -> str:
        """The stack copy this environment reaches, or nothing when no host is one ostler runs."""
        for url in self.hosts.values():
            if url.startswith(OSTLER):
                return self._copy_of(url)
        return ""

    def _copy_of(self, url: str) -> str:
        """The copy the run named, else the lease the process runs under, else the one the book names, else the
        shared one. A book's own name is a default for a run by hand, so whoever runs the book outranks it."""
        return self.leased or os.environ.get(LEASE_ENV, "") or url[len(OSTLER):] or SHARED

    def variables(self) -> dict[str, str]:
        return {PREFIX + handle.upper(): secret for handle, secret in self.secrets.items()}

    def missing(self, present: Mapping[str, str] | None = None) -> dict[str, str]:
        have = os.environ if present is None else present
        return {var: secret for var, secret in self.variables().items() if var not in have}


def exec_command(environment: Environment, argv: list[str], present: Mapping[str, str] | None = None) -> list[str] | None:
    """The command that runs this one again under saddlebag, or None when every variable is already set."""
    missing = environment.missing(present)
    if not missing:
        return None
    command = ["saddlebag", "exec"]
    for var, secret in missing.items():
        command += ["--env", f"{var}={secret}"]
    return [*command, "--", "python3", "-m", "ostler.book", *argv]


def credentials(environment: Environment, argv: list[str], print_only: bool = False) -> int | None:
    """Re-executes the command under saddlebag when a secret's variable is absent. Returns an exit code when
    the process should stop instead of going on."""
    command = exec_command(environment, [a for a in argv if a != "--print-exec"])
    if print_only:
        print(" ".join(command) if command else f"no re-exec: every BOOK_SECRET_ variable of {environment.name} is present")
        return 0
    if command is None:
        return None
    if os.environ.get(GUARD):
        print("saddlebag exec ran and left " + ", ".join(environment.missing()) + " unset")
        return 2
    os.environ[GUARD] = "1"
    os.execvp(command[0], command)
    return 2
