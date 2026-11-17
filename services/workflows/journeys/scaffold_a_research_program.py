from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look, NewProgram
from ..fixtures import OTHER_GATE, program


class ScaffoldAResearchProgram(Journey):
    """A person stamps a research program folder before running the research workflow. The folder holds the manifest,
    the README, the progress log and the first gate. Stamping it again is refused and leaves the files alone. With
    --force, another first gate and --set-default the files are written again, a second gate file sits beside the
    first, and the active program is pointed at the folder. A missing folder or source folder stops at the usage line."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            NewProgram(program(None, code_root=None)),
            NewProgram(program(None)),
            NewProgram(program(code_root=None)),
            Look(),
            NewProgram(program()),
            Look(),
            NewProgram(program()),
            NewProgram(program(gate=OTHER_GATE, set_default=True, force=True)),
            Look(),
        )
