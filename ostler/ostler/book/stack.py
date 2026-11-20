"""The processes a surface needs running, started and stopped by ostler."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from ostler.book.workspace import checkout


def _copy(source: IO[bytes], log: IO[bytes]) -> None:
    for raw in source:
        log.write(raw)
        log.flush()


@dataclass
class Process:
    """One program the surface needs. `ready` is the text it prints once it
    serves; start returns when a line holds it."""

    name: str
    command: list[str]
    cwd: str
    ready: str
    env: dict[str, str] = field(default_factory=dict)
    handle: subprocess.Popen[bytes] | None = None

    def start(self, log_dir: str) -> None:
        if self.handle is not None:
            return
        os.makedirs(log_dir, exist_ok=True)
        log = open(os.path.join(log_dir, f"{self.name}.log"), "ab")
        self.handle = subprocess.Popen(
            self.command, cwd=self.cwd, env={**os.environ, **self.env},
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True,
        )
        assert self.handle.stdout is not None
        last: list[str] = []
        for raw in self.handle.stdout:
            log.write(raw)
            log.flush()
            line = raw.decode(errors="replace").rstrip()
            last = [*last, line][-10:]
            if self.ready in line:
                threading.Thread(target=_copy, args=(self.handle.stdout, log), daemon=True).start()
                return
        self.handle.wait()
        code, self.handle = self.handle.returncode, None
        raise RuntimeError(f"{self.name} exited with {code} before printing {self.ready!r}:\n" + "\n".join(last))

    def stop(self) -> None:
        if self.handle is None:
            return
        os.killpg(self.handle.pid, signal.SIGTERM)
        try:
            self.handle.wait(10)
        except subprocess.TimeoutExpired:
            os.killpg(self.handle.pid, signal.SIGKILL)
        self.handle = None


@dataclass(frozen=True)
class Fresh:
    """The command that returns the application's data to its loaded state and returns once the application answers.
    `cwd` is `repo://<member>/<path>`, an absolute path, or a path under the book root; empty is the book root."""

    command: tuple[str, ...]
    cwd: str = ""
    timeout: float = 600.0

    def directory(self) -> str:
        if self.cwd.startswith("repo://"):
            member, _slash, rest = self.cwd.removeprefix("repo://").partition("/")
            return str(Path(checkout(member)) / rest)
        return str(Path.cwd() / self.cwd)

    def run(self) -> tuple[str, float, str]:
        """How the reload ended (`ok`, an exit code, or `timed out`), the seconds it took and the tail of its output."""
        began = time.time()
        try:
            done = subprocess.run(self.command, cwd=self.directory(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as late:
            return "timed out", time.time() - began, "\n".join((late.stdout or b"").decode(errors="replace").splitlines()[-20:])
        except OSError as broken:
            return "1", time.time() - began, str(broken)
        shown = "\n".join(done.stdout.decode(errors="replace").splitlines()[-20:])
        return ("ok" if done.returncode == 0 else str(done.returncode)), time.time() - began, shown


@dataclass
class Stack:
    processes: tuple[Process, ...]
    log_dir: str
    fresh: Fresh | None = None

    def start(self) -> None:
        for process in self.processes:
            process.start(self.log_dir)

    def stop(self) -> None:
        for process in reversed(self.processes):
            process.stop()
