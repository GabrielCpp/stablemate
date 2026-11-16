from datetime import date

from ostler.book import Journey

from ..fixtures import Who, todo
from ..interactions import AddTodo, GoBack, GoToAssign, PickAssignee


class AnAssigneeIsPickedAfterANavigation(Journey):
    """Ana writes a chore down, follows the link to the assign page, picks Bo and goes back."""

    def steps(self, today: date):
        yield AddTodo(todo("Sort the photos"))
        yield GoToAssign()
        yield PickAssignee(Who("bo"))
        yield GoBack()
