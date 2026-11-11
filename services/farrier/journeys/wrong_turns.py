from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Init, Install, Scaffold
from ..fixtures import init, install, scaffold


class WrongTurns(Journey):
    """A person runs farrier out of order. install with no agents.yml is told to run init. A scaffold on a repo with
    no agents.yml is offered everything the library defines. After init, a scaffold the config does not list is not
    enabled, an unknown one is refused with the ids the library defines, and a library that does not exist is
    refused before anything else is read."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            Install(install()),
            Scaffold(scaffold()),
            Init(init(force=True)),
            Scaffold(scaffold(dir="backend")),
            Scaffold(scaffold("nonesuch")),
            Install(install(library="no-such-lib")),
            Init(init(repo="no-such-dir")),
        )
