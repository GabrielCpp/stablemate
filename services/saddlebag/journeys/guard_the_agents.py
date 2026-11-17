from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import LeaveSettings


class GuardTheAgents(Journey):
    """A person registers the guard in a project's settings and in their own, once in a project that already has
    settings of its own. The guard then refuses an agent action that reads a dotenv, a key file or an export and says
    how to get the same thing, lets the examples, the other actions and `saddlebag exec` through, and ignores what is no
    JSON. A bare `saddlebag guard`, and an install that names neither or both scopes, are refused."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.GuardBare(f.GuardBareArgs()),
            c.GuardInstall(f.install_guard(project=None)),
            c.GuardInstall(f.install_guard(user=True)),
            LeaveSettings(),
            c.GuardInstall(f.install_guard()),
            c.GuardInstall(f.install_guard(user=True, project=None)),
            c.GuardInstall(f.install_guard()),
            c.GuardHook(f.hook()),
            c.GuardHook(f.hook(f.KEY_PAYLOAD)),
            c.GuardHook(f.hook(f.EXPORT_PAYLOAD)),
            c.GuardHook(f.hook(f.ALLOW_PAYLOAD)),
            c.GuardHook(f.hook(f.EXAMPLE_PAYLOAD)),
            c.GuardHook(f.hook(f.EXEC_PAYLOAD)),
            c.GuardHook(f.hook("not json")),
        )
