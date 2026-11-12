from datetime import date

from ostler.book import Journey

from ..endpoints import PushProgress, ReadFleet
from ...fixtures import Query, running, stranger


class FindingARun(Journey):
    """Two runs are on the fleet. Typing one's name keeps that run and drops the other, and a
    name no run has keeps neither."""

    def steps(self, today: date):
        first, second = running(), running()
        yield PushProgress(first.but(current_node="plan"))
        yield PushProgress(second.but(current_node="plan"))
        yield ReadFleet(query=Query(q=first.name))
        yield ReadFleet(query=Query(q=second.name))
        yield ReadFleet(query=Query(q=stranger().name))
