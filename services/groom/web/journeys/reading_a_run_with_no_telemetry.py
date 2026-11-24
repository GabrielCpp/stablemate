from datetime import date

from ostler.book import Journey

from ...fixtures import running
from ..interactions import OpenRun, ReadActivity, ReportProgress


class ReadingARunWithNoTelemetry(Journey):
    """A workflow pushes progress and nothing else, so groom holds no span of the run. The operator
    opens the run and its Activity tab, which says the run has no telemetry in place of a timeline."""

    def steps(self, today: date):
        run = running(current_node="build")
        yield ReportProgress(run)
        yield OpenRun(run)
        yield ReadActivity(run)
