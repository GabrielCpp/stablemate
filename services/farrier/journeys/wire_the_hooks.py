from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f


class WireTheHooks(Journey):
    """A person checks a repository with no agents.yml and is told to run init. After init the doctor warns that no services are declared. Hooks list says there is no library, hooks install announces its steps with --dry-run and then wires them. The commit checks and the sync print nothing. Once the library is recorded the listing shows each stage empty."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Doctor(f.doctor()),
            c.HooksList(f.hooks_list()),
            c.Init(f.init()),
            c.Doctor(f.doctor()),
            c.Doctor(f.doctor(repo="no-such-dir")),
            c.HooksList(f.hooks_list()),
            c.HooksList(f.hooks_list(repo="no-such-dir")),
            c.HooksInstall(f.hooks_install(dry_run=True)),
            c.HooksInstall(f.hooks_install()),
            c.Checks(f.ChecksArgs()),
            c.Sync(f.SyncArgs()),
            c.ConfigSetLibrary(f.set_library()),
            c.HooksList(f.hooks_list()),
            c.Checks(f.ChecksArgs()),
            c.Look(),
        )
