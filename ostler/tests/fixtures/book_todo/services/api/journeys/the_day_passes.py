from datetime import date, timedelta

from ostler.book import Journey, Listed

from ..endpoints import AddTodo, FindTodos, SetClock, UpdateTodo
from ..fixtures import Clock, Query, scheduled, todo


class TheDayPasses(Journey):
    """Bo schedules two chores for tomorrow and the day after, then two days go by.
    The first is overdue and rises to the top of the list; Bo can still rename it
    and keep its day, cannot move it to another day that has passed, and can push
    it to today."""

    alone = True

    def steps(self, today: date):
        books = scheduled(today, 1, title="Return the library books", assignee="bo")
        passport = scheduled(today, 2, title="Renew the passport", assignee="bo")
        yield AddTodo(books)
        yield AddTodo(passport)
        garden = todo("Think about the garden")
        yield AddTodo(garden)
        yield Listed(books, passport, garden)
        yield SetClock(Clock("next tuesday"))
        yield SetClock(Clock(today + timedelta(days=2)))
        yield FindTodos(query=Query(status="overdue"))
        yield UpdateTodo(books.set(title="Return the overdue library books"))
        yield UpdateTodo(books.but(due_on=today))
        yield UpdateTodo(books.set(due_on=today + timedelta(days=2)))
        yield Listed(books, passport, garden)
