from datetime import date, timedelta

from ostler.book import Journey, Listed

from ..fixtures import scheduled
from ..interactions import AddTodo, EditTodo


class EditKeepsWhatWasTyped(Journey):
    """Bo edits a chore and moves its date to last week by mistake. The form is
    refused with the reason, keeps what he typed, and the row is untouched. He
    fixes the date and saves."""

    def steps(self, today: date):
        fence = scheduled(today, 3, title="Paint the fence", assignee="bo")
        yield AddTodo(fence)
        yield EditTodo(fence.but(title="Paint the back fence", due_on=today - timedelta(days=7)))
        yield Listed(fence)
        yield EditTodo(fence.set(title="Paint the back fence", due_on=today + timedelta(days=4)))
        yield Listed(fence)
