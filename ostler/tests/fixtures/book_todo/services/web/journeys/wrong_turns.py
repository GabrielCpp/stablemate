from datetime import date, timedelta

from ostler.book import Journey, Listed

from ..fixtures import assigned, blank_title, past_due, scheduled
from ..interactions import AddTodo, EditTodo


class WrongTurns(Journey):
    """Ana makes the mistakes a form lets her make: a blank title, a date that
    has passed, a colleague who does not exist. Each is turned away with its
    reason and the list is as it was. Then she gets it right."""

    def steps(self, today: date):
        rent = scheduled(today, 3, title="Pay the rent")
        yield AddTodo(rent)
        yield AddTodo(blank_title())
        yield AddTodo(past_due(today, title="Book the dentist"))
        yield AddTodo(assigned("cy", title="Book the dentist"))
        yield Listed(rent)
        yield EditTodo(rent.but(due_on=today - timedelta(days=30)))
        yield EditTodo(rent.but(title=""))
        dentist = scheduled(today, 0, title="Book the dentist", assignee="bo")
        yield AddTodo(dentist)
        yield Listed(dentist, rent)
