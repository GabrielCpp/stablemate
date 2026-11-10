from datetime import date

from ostler.book import Journey, Listed

from ..endpoints import AddTodo, RemoveTodo
from ..fixtures import todo


class ClearTheList(Journey):
    """At the end of the week Ana removes everything, one chore at a time, and the
    list says there is nothing to do. Removing one twice is turned away."""

    def steps(self, today: date):
        vacuum, dust, water = todo("Vacuum"), todo("Dust the shelves"), todo("Water the plants")
        yield AddTodo(vacuum)
        yield AddTodo(dust)
        yield AddTodo(water)
        yield RemoveTodo(dust)
        yield RemoveTodo(vacuum)
        yield RemoveTodo(water)
        yield Listed()
        yield RemoveTodo(vacuum)
