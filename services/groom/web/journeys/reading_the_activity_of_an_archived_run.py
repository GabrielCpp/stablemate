from datetime import date

from ostler.book import Journey

from ...fixtures import archived
from ..interactions import OpenHistory, ReadAnArchivedActivity


class ReadingTheActivityOfAnArchivedRun(Journey):
    """Groom froze a finished run into an archive. The operator opens History, opens the archived run
    and reads its Activity tab: the timeline with its filters and keys, a turn read from the archive,
    and the same problem count on the Overview link, the control and the tab."""

    def steps(self, today: date):
        yield OpenHistory()
        yield ReadAnArchivedActivity(archived())
