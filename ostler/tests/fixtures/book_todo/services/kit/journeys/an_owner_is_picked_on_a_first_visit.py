from datetime import date

from ostler.book import Journey

from ..fixtures import todo
from ..interactions import AddTodo


class AnOwnerIsPickedOnAFirstVisit(Journey):
    """Ana opens the app, writes a chore down and hands it to Bo from the list the page was handed."""

    def steps(self, today: date):
        yield AddTodo(todo("Buy milk", assignee="bo"))
