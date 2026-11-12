from datetime import date

from ostler.book import Journey

from ..fixtures import Query, running
from .endpoints import PushProgress, ReadAttend, ReadFleet, ReadWorker


class TheFleetAnswers(Journey):
    """What every other journey stands on, read before any of them runs. A run that
    reports can be found on the fleet and opened, and the attendant switch can be read."""

    def steps(self, today: date):
        probe = running()
        yield PushProgress(probe)
        yield ReadFleet(query=Query(q=probe.name))
        yield ReadWorker(probe)
        yield ReadAttend()
