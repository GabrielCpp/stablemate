from datetime import date

from ostler.book import Journey

from ..fixtures import running
from .interactions import OpenRuns, OpenSettings, ReportProgress


class TheDashboardShowsTheFleet(Journey):
    """What every other journey stands on, read before any of them runs. The page opens, a
    run that reports shows on its list, and the settings pane opens and closes."""

    def steps(self, today: date):
        yield ReportProgress(running())
        yield OpenSettings()
        yield OpenRuns()
