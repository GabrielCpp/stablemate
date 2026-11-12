from datetime import date

from ostler.book import Journey

from ..endpoints import PushBlocked, PushExited, PushProgress, ReadFleet
from ...fixtures import Query, blocked, finished, running


class TheFleetIsOrdered(Journey):
    """Three runs report in the order finished, running, blocked. The fleet puts the blocked
    one first, then the running one, then the finished one, and the attention list names
    the blocked and the ended run."""

    def steps(self, today: date):
        done, going, waiting = finished(0), running(current_node="build"), blocked()
        yield PushExited(done)
        yield PushProgress(going)
        yield PushBlocked(waiting)
        yield ReadFleet(query=Query())
