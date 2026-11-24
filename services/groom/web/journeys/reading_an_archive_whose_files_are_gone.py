from datetime import date

from ostler.book import Journey

from ...fixtures import archived
from ..interactions import OpenHistory, ReadAnArchivedActivity


class ReadingAnArchiveWhoseFilesAreGone(Journey):
    """Groom kept the summary of an archived run and lost its folder. The operator opens the run in
    History and its Activity tab says the activity cannot be read, while the Overview keeps the summary."""

    def steps(self, today: date):
        yield OpenHistory()
        yield ReadAnArchivedActivity(archived(gone=True))
