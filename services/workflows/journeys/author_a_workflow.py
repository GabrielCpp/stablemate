from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look, New
from ..fixtures import OTHER_CHECK, new


class AuthorAWorkflow(Journey):
    """A person scaffolds a workflow of their own with workhorse-new. The distribution lands in the working
    directory with the check written into its README and workflow. Asking for the same name again is refused and
    leaves what is there alone. The same name into another directory, with another check, is a second distribution."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            New(new()),
            Look(),
            New(new()),
            New(new(check=OTHER_CHECK, into="elsewhere")),
            Look(),
        )
