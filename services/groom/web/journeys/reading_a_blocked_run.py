from datetime import date

from ostler.book import Journey

from ...fixtures import blocked, replying
from ..interactions import AnswerTheGate, OpenRun, ReportGate


class ReadingABlockedRun(Journey):
    """A run asks the operator a question. The operator opens the run, sees the gate it waits on, and
    types an answer. groom cannot reach the run's workspace, so it refuses the answer and says why,
    and the run stays blocked on the list."""

    def steps(self, today: date):
        run = blocked()
        yield ReportGate(run)
        yield OpenRun(run)
        yield AnswerTheGate(replying(run.container_id, "yes"))
