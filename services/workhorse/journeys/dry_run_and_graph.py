from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Dot, Look, Run, Version
from ..fixtures import dot, run, version


class DryRunAndGraph(Journey):
    """A person checks the install, rehearses the loop without an agent, and looks at the flow it walked. They read the
    version, run once into the default directory and once into another, print the flow as a graph, name it, and
    write both graphs to files."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            Version(version()),
            Run(run()),
            Run(run(runs_dir="elsewhere")),
            Look(),
            Dot(dot()),
            Dot(dot("chart")),
            Dot(dot(out="out.dot")),
            Dot(dot("chart", "chart.dot")),
            Look(),
        )
