from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Init, Install, Scaffold
from ..events import ListWhatIsWanted
from ..fixtures import init, install, scaffold


class SetUpARepo(Journey):
    """A person starts a repository with farrier. They write the starter agents.yml, list the demo skill and the
    scaffold in it as the Next line asks, render the install, and seed a folder from the scaffold twice into two
    places. Running the scaffold again keeps what it wrote."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            Init(init()),
            ListWhatIsWanted(),
            Install(install()),
            Scaffold(scaffold(dir="backend")),
            Scaffold(scaffold(None)),
            Scaffold(scaffold()),
            Scaffold(scaffold(dir="backend")),
        )
