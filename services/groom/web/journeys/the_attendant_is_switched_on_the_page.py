from datetime import date

from ostler.book import Journey

from ...fixtures import Settings
from ..interactions import OpenRuns, OpenSettings, SwitchTheAttendant


class TheAttendantIsSwitchedOnThePage(Journey):
    """An operator opens Settings, ticks the attendant box, clears it, and goes back to the
    runs. The pane names the mode each time, and the mode is kept across the return."""

    def steps(self, today: date):
        yield OpenSettings()
        yield SwitchTheAttendant(Settings(enabled=True))
        yield OpenRuns()
        yield OpenSettings()
        yield SwitchTheAttendant(Settings(enabled=False))
        yield OpenRuns()
