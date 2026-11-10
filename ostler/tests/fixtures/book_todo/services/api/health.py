from datetime import date

from ostler.book import Journey

from .endpoints import AddTodo, ReadTodo, RemoveTodo
from .fixtures import todo


class TheStoreAnswers(Journey):
    """What every other journey stands on, read before any of them runs. The store is up,
    so a todo written can be read back and removed again."""

    def steps(self, today: date):
        probe = todo("Health check")
        yield AddTodo(probe)
        yield ReadTodo(probe)
        yield RemoveTodo(probe)
