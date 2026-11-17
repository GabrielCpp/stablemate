from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from .. import commands as c
from .. import fixtures as f
from ..events import ListUserLibrary, ListWhatIsWanted


class ReleaseAndTraceASkill(Journey):
    """A person installs the demo skill and asks where the generated file comes from. They are told the library file. A file farrier did not write and a file that is not there are refused. They eject the skill, which hands the folder over and drops the selection. A second eject finds nothing to hand over, and the same file now names no source."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            c.Init(f.init()),
            ListWhatIsWanted(),
            c.Install(f.install()),
            c.Source(f.source()),
            c.Source(f.source("agents.yml")),
            c.Source(f.source("nonesuch")),
            c.Eject(f.eject("demo")),
            c.Eject(f.eject()),
            c.Eject(f.eject()),
            c.Source(f.source()),
            c.Look(),
        )
