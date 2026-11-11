"""A place a service runs: the hosts that reach it, the saddlebag secrets its
cast signs in with, and the backstage that can arrange state there. The book
holds secret names only. A value reaches the process through the environment
variable `BOOK_SECRET_<HANDLE>`, which saddlebag fills."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass, field
from typing import Mapping

from ostler.book.errors import BookError
from ostler.environments.render import SHARED
from ostler.qa.addresses import LEASE_ENV

OSTLER = "ostler:"
PREFIX = "BOOK_SECRET_"
GUARD = "BOOK_REEXEC"


@dataclass
class Environment:
    name: str
    hosts: dict[str, str]
    secrets: dict[str, str] = field(default_factory=dict)
    backstage: type | None = None
    root: str = ""
    leased: str = ""

    def address(self, host: str) -> str:
        if host not in self.hosts:
            raise BookError(f"environment {self.name!r} knows no host called {host!r}")
        url = self.hosts[host]
        if not url.startswith(OSTLER):
            return url
        done = subprocess.run(["ostler", "env", "address", host, "--copy", self._copy_of(url)], cwd=self.root or None,
                              capture_output=True, text=True, check=False)
        if done.returncode:
            raise RuntimeError(done.stderr or done.stdout)
        return done.stdout.strip()

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
