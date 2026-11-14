from datetime import date

from ostler.book import Journey, Needs

from ..endpoints import ReadDigest, ReadDigestEntry
from ..foreign import TODO


class AnOverdueTodoIsInTheDigest(Journey):
    """Ana has a chore that is past its due day and another that is not yet due. The digest lists
    the first among the late ones and leaves the second out, and reading the first by its id says
    it is late."""

    chore = Needs(TODO, "overdue")
    later = Needs(TODO, "scheduled")
    given = (chore, later)

    def steps(self, today: date):
        yield ReadDigest()
        yield ReadDigestEntry(self.chore)
