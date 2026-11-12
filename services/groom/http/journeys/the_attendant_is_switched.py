from datetime import date

from ostler.book import Journey

from ..endpoints import ReadAttend, ReadFleet, SetAttend
from ...fixtures import Query, Settings


class TheAttendantIsSwitched(Journey):
    """The operator turns the attendant on, sees the fleet report it, turns it off again, and
    sees the switch back where it began."""

    alone = True

    def steps(self, today: date):
        yield ReadAttend()
        yield SetAttend(Settings(enabled=True))
        yield ReadAttend()
        yield ReadFleet(query=Query())
        yield SetAttend(Settings(enabled=False))
        yield ReadAttend()
        yield ReadFleet(query=Query())
