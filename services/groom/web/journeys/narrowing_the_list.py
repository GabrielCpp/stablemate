from datetime import date

from ostler.book import Journey

from ...fixtures import Query, on_branch, running
from ..interactions import FilterTheList, ReportProgress


class NarrowingTheList(Journey):
    """An operator types in the filter box. The list keeps the runs that hold the text in their
    name, repo or node, matches without regard to case or the spaces around it, and shows every
    run again once the box is cleared."""

    def steps(self, today: date):
        shop = on_branch("shop", "main")
        other = running(repo_name="billing", repo_branch="dev")
        yield ReportProgress(shop)
        yield ReportProgress(other)
        yield FilterTheList(Query(q=shop.name))
        yield FilterTheList(Query(q="  SHOP "))
        yield FilterTheList(Query(q="billing"))
        yield FilterTheList(Query(q="nothing-runs-here"))
        yield FilterTheList(Query())
