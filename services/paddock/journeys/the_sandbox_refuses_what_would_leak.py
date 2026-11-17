from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class TheSandboxRefusesWhatWouldLeak(Journey):
    """A maintainer sets up a sandboxed book run. The command after `--` is needed, the config must be readable and
    may only name claude or opencode, and each login it names must exist. Each app must exist and carry its own
    directory name. With several apps the command must say which one it starts in, and that name must be one of them.
    Every refusal comes before docker is asked for anything."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.SandboxRun(f.sandbox_run(command=None)),
            c.SandboxRun(f.sandbox_run(config="sbx/none.toml")),
            c.SandboxRun(f.sandbox_run(config=f.GEMINI)),
            c.SandboxRun(f.sandbox_run("sbx/apps/nodir")),
            c.SandboxRun(f.sandbox_run(f"{f.APPS}/api", f"{f.OTHER}/api")),
            c.SandboxRun(f.sandbox_run(config=f.CLAUDE)),
            c.SandboxRun(f.sandbox_run(config=f.OPENCODE)),
            c.SandboxRun(f.sandbox_run(f"{f.APPS}/api", f"{f.APPS}/web")),
            c.SandboxRun(f.sandbox_run(workdir="zzz")),
        )
