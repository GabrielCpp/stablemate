from datetime import date

from ostler.book import Journey, Needs

from ..endpoints import FinishFromDigest, ReadDigest
from ..foreign import TODO


class AnOverdueTodoIsFinishedFromTheDigest(Journey):
    """Ana finishes her overdue chore from the digest. The todo API then holds no such todo, and the
    digest no longer lists it."""

    chore = Needs(TODO, "overdue")
    given = (chore,)

    def steps(self, today: date):
        yield FinishFromDigest(self.chore)
        yield ReadDigest()
