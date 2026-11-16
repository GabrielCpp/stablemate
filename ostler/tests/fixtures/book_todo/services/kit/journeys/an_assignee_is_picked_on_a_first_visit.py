from datetime import date

from ostler.book import Journey

from ..fixtures import Who
from ..interactions import OpenAssign, PickAssignee


class AnAssigneeIsPickedOnAFirstVisit(Journey):
    """Bo types the address of the assign page and picks Ana."""

    def steps(self, today: date):
        yield OpenAssign()
        yield PickAssignee(Who("ana"))
