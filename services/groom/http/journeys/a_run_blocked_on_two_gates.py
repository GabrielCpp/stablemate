from datetime import date

from ostler.book import Journey

from ..endpoints import PushBlocked, PushExited, ReadFleet, ReadWorker
from ...fixtures import Query, running


class ARunBlockedOnTwoGates(Journey):
    """A run asks two questions at once, the later path first. The page lists the gates by
    path, a second ask at a path replaces its question, and an exit clears them all."""

    def steps(self, today: date):
        run = running()
        yield PushBlocked(run.but(file_path="gates/z-review.md", question="Is the review done?"))
        yield PushBlocked(run.but(file_path="gates/a-approve.md", question="Ship it?"))
        yield ReadWorker(run)
        yield ReadFleet(query=Query(q=run.name))
        yield PushBlocked(run.but(file_path="gates/a-approve.md", question="Ship it on Friday?"))
        yield ReadWorker(run)
        yield PushExited(run.but(exit_code=0))
        yield ReadWorker(run)
        yield ReadFleet(query=Query(q=run.name))
