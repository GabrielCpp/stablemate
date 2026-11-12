from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look, Run
from ..fixtures import MISSING, NOT_AN_OBJECT, NOT_JSON, run


class RunRefusals(Journey):
    """A person starts a run with flags that cannot work. A backend the runner does not know, a backend together with a
    profile, a profile or config or workspace or context file that is not there, parameters that are not JSON or not an
    object, a parameters file that is missing, and a run to resume that is missing. The runner refuses each before it
    writes any run."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            Run(run(cli=MISSING)),
            Run(run(cli="claude", profile=MISSING)),
            Run(run(profile=MISSING)),
            Run(run(config=MISSING)),
            Run(run(params=NOT_JSON)),
            Run(run(params=NOT_AN_OBJECT)),
            Run(run(params_file=MISSING)),
            Run(run(workspace=MISSING)),
            Run(run(context_file=MISSING)),
            Run(run(resume_run=MISSING)),
            Look(),
        )
