from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Look, New
from ..fixtures import new


class WrongTurns(Journey):
    """A person mistypes workhorse-new. A name with capital letters is refused with the rule for names, a blank check
    is refused, and a missing name or check stops at the usage line. Nothing is written by any of them."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            New(new("Fix-Tests")),
            New(new(check="  ")),
            New(new(check=None)),
            New(new(None)),
            New(new(None, check=None)),
            Look(),
        )
