from datetime import date

from ostler.book import Journey

from ...fixtures import blocked, finished, running
from ..interactions import ReportExit, ReportGate, ReportProgress


class TheListIsOrdered(Journey):
    """Three runs report in the order finished, running, blocked. The list puts the blocked
    run first, the running one next and the ended one last."""

    def steps(self, today: date):
        done = finished(0)
        live = running()
        stuck = blocked()
        yield ReportExit(done)
        yield ReportProgress(live)
        yield ReportGate(stuck)
