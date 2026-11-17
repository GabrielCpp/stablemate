from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import ListUserLibrary, ListWhatIsWanted


class InstallForEveryRepo(Journey):
    """A person installs the user library before the home config has one and is refused. They add a table that names the demo skill, install again and the skill lands in the home. Installing again changes nothing."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.InstallUser(f.install_user()),
            ListUserLibrary(),
            c.InstallUser(f.install_user()),
            c.InstallUser(f.install_user()),
            c.Look(),
        )
