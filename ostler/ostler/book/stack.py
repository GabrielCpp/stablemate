"""The processes a surface needs running, started and stopped by ostler."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
from dataclasses import dataclass, field
from typing import IO


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


@dataclass
class Stack:
    processes: tuple[Process, ...]
    log_dir: str

    def start(self) -> None:
        for process in self.processes:
            process.start(self.log_dir)

    def stop(self) -> None:
        for process in reversed(self.processes):
            process.stop()
