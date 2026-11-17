from datetime import date

from ostler.book import Journey

from ..interactions import OpenAttendant, OpenDispatch, OpenHistory, OpenRuns, OpenSettings


class LookingThroughThePanes(Journey):
    """An operator walks the left bar. History lists no ended run, the attendant has sent an agent at
    nothing, no dispatch queue is configured, and the settings pane opens. The run list is where
    they come back to."""

    def steps(self, today: date):
        yield OpenHistory()
        yield OpenAttendant()
        yield OpenDispatch()
        yield OpenSettings()
        yield OpenRuns()
