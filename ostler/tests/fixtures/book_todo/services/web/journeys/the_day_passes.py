from datetime import date, timedelta

from ostler.book import Journey, Listed, Needs

from ...api.people import ANA
from ..fixtures import Clock, Query, scheduled, todo
from ..foreign import TODO, standing
from ..interactions import AddTodo, DayPasses, EditTodo, Filter


class TheDayPasses(Journey):
    """Bo starts with a chore that is already overdue and adds two more for the coming days. Two days
    go by. The second is overdue too and rises with the first; Bo can still rename the first, and can
    push it ahead, but not to a day that has passed."""

    alone = True
    chore = Needs(TODO, "overdue", ANA)
    given = (chore,)

    def steps(self, today: date):
        gate = standing(self.chore)
        passport = scheduled(today, 1, title="Renew the passport", assignee="bo")
        garden = todo("Think about the garden")
        yield AddTodo(passport)
        yield AddTodo(garden)
        yield Listed(gate, passport, garden)
        yield DayPasses(Clock(today + timedelta(days=2)))
        yield Filter(Query(status="overdue"))
        yield EditTodo(gate.set(title="Mend the overdue gate"))
        yield EditTodo(gate.but(due_on=today))
        yield EditTodo(gate.set(due_on=today + timedelta(days=4)))
        yield Listed(passport, gate, garden)
