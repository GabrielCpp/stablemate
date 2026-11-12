from datetime import date

from ostler.book import Journey

from ..endpoints import PushBlocked, PushExited, PushProgress, ReadFleet, ReadWorker
from ...fixtures import Push, Query, running, stranger, unreported


class UnknownRuns(Journey):
    """A push that names no run is ignored, a gate needs a path as well, and asking for a run
    nobody pushed gets a page that says it was not found. A run that exits before it ever
    reported still lands on the fleet, shown by its id."""

    def steps(self, today: date):
        nameless = Push()
        yield PushProgress(nameless)
        yield PushExited(nameless)
        pathless = running()
        yield PushBlocked(pathless)
        yield ReadWorker(pathless)
        yield ReadWorker(stranger())
        late = unreported(exit_code=3)
        yield PushExited(late)
        yield ReadWorker(late)
        yield ReadFleet(query=Query(q=late.container_id))
