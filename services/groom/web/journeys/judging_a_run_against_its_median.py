from datetime import date

from ostler.book import Journey

from ...fixtures import judging
from ..interactions import OpenHistory, ReadTheMedian, ReadTheOpenedRun


class JudgingARunAgainstItsMedian(Journey):
    """An operator opens History after five runs of a workflow and a sixth that cost more per item
    ended. Choosing the workflow, the sixth run reads its cost per item with a signed percent against
    the median of the five others, and the totals read the median of all six. Opening the sixth run, its
    Work items tile reads the same percent in words and the By node table reads its agent node against
    the median of the five."""

    def steps(self, today: date):
        yield OpenHistory()
        judged = judging()
        yield ReadTheMedian(judged)
        yield ReadTheOpenedRun(judged)
