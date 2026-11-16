from datetime import date

from ostler.book import Journey

from ..fixtures import todo
from ..interactions import AddTodo, GoBack, GoToAssign


class AnOwnerIsPickedAfterANavigation(Journey):
    """Ana looks at the assign page, comes back by its link, and writes a chore for herself."""

    def steps(self, today: date):
        yield GoToAssign()
        yield GoBack()
        yield AddTodo(todo("Water the plants", assignee="ana"))
