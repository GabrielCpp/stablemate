from datetime import date

from ostler.book import Journey

from ...fixtures import judging
from ..interactions import OpenHistory, ReadTheMedian


class JudgingARunAgainstItsMedian(Journey):
    """An operator opens History after five runs of a workflow and a sixth that cost more per item
    ended. Choosing the workflow, the sixth run reads its cost per item with a signed percent against
    the median of the five others, and the totals read the median of all six."""

    def steps(self, today: date):
        yield OpenHistory()
        yield ReadTheMedian(judging())
