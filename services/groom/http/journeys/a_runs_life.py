from datetime import date

from ostler.book import Journey

from ..endpoints import PushBlocked, PushExited, PushProgress, ReadFleet, ReadWorker
from ...fixtures import Query, on_branch


class ARunsLife(Journey):
    """A workflow starts on a branch, moves through two nodes, stops to ask the operator,
    carries on after the answer, and ends with a failure. At every stage the fleet and
    the run's page say where it is."""

    def steps(self, today: date):
        run = on_branch("shop", "main")
        yield PushProgress(run.but(current_node="plan"))
        yield ReadFleet(query=Query(q=run.name))
        yield ReadWorker(run)
        yield PushProgress(run.but(current_node="build"))
        yield ReadWorker(run)
        yield PushBlocked(run.but(file_path="gates/approve.md", question="Ship it?"))
        yield ReadFleet(query=Query(q=run.name))
        yield ReadWorker(run)
        yield PushProgress(run.but(current_node="ship"))
        yield ReadFleet(query=Query(q=run.name))
        yield PushExited(run.but(exit_code=1))
        yield ReadFleet(query=Query(q=run.name))
        yield ReadWorker(run)
