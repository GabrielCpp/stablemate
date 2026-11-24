from datetime import date

from ostler.book import Journey

from ...fixtures import archived
from ..interactions import OpenHistory, ReadArchiveRecords


class ReadingTheRecordsOfAnArchivedRun(Journey):
    """Groom froze a finished run with its logs and metric samples. The operator opens the archived run
    in History, reads Raw newest first, asks for the metric samples and for older records, then searches
    the rows and the transcripts."""

    def steps(self, today: date):
        yield OpenHistory()
        yield ReadArchiveRecords(archived())
