from datetime import date, timedelta

from ostler.book import Journey, Listed

from ..fixtures import Clock, Query, scheduled, todo
from ..interactions import AddTodo, DayPasses, EditTodo, Filter


class TheDayPasses(Journey):
    """Bo schedules two chores for tomorrow and the day after, then two days go by.
    The first is overdue and rises to the top of the list; Bo can still rename it,
    and can push it to today, but not to a day that has passed."""

    alone = True

    def steps(self, today: date):
        books = scheduled(today, 1, title="Return the library books", assignee="bo")
        passport = scheduled(today, 2, title="Renew the passport", assignee="bo")
        garden = todo("Think about the garden")
        yield AddTodo(books)
        yield AddTodo(passport)
        yield AddTodo(garden)
        yield Listed(books, passport, garden)
        yield DayPasses(Clock(today + timedelta(days=2)))
        yield Filter(Query(status="overdue"))
        yield EditTodo(books.set(title="Return the overdue library books"))
        yield EditTodo(books.but(due_on=today))
        yield EditTodo(books.set(due_on=today + timedelta(days=2)))
        yield Listed(books, passport, garden)
