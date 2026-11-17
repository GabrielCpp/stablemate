from datetime import date

from ostler.book import Journey

from ...fixtures import asking, looking_at
from .. import endpoints as e


class NothingIsArchived(Journey):
    """An operator looks for a finished run in the archive and in the history. groom has archived
    nothing, so each archive read says no run is archived under that id, the history lists no
    ended run of ours, and asking to read a summary again changes nothing."""

    def steps(self, today: date):
        look = looking_at()
        yield e.ReadArchiveOverview(look)
        yield e.ReadArchiveActivity(look.but(logs=1))
        yield e.ReadArchiveRecords(look.but(limit=5))
        yield e.SearchArchive(look.but(q="deploy"))
        yield e.ReadArchiveEntry(look.but(key="step:plan"))
        yield e.ReadArchiveTurn(look.but(slug="plan-1"))
        yield e.ReadHistory(query=asking())
        yield e.ReadHistory(query=asking(archives=1))
        yield e.RetryHistory(look)
