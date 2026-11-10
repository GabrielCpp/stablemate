from datetime import date

from ostler.book import Given, Journey

from ..endpoints import AddTodo, FindTodos, ReadTodo, RemoveTodo, SetStore, UpdateTodo
from ..fixtures import Switch, stranger, todo


class TheStoreIsDown(Journey):
    """The store is unreachable. Nothing can be added or read, and the service
    says so instead of pretending."""

    alone = True

    given = (Given(SetStore(Switch(down=True)), undo=SetStore(Switch(down=False))),)

    def steps(self, today: date):
        yield AddTodo(todo("Anything at all"))
        yield FindTodos()
        yield ReadTodo(stranger())
        yield UpdateTodo(stranger())
        yield RemoveTodo(stranger())
