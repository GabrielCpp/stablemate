from datetime import date, timedelta

from ostler.book import Journey, Listed

from ..fixtures import Query, described, scheduled, todo
from ..interactions import AddTodo, EditTodo, Filter, RemoveTodo


class AWeekOfChores(Journey):
    """Ana plans her week. She writes down three chores, one with no date yet,
    hands one to Bo, finishes one and crosses it off, renames another, and
    moves the first one's due date back a day. Then she looks at what is left
    for her."""

    def steps(self, today: date):
        milk = scheduled(today, 1, title="Buy milk", assignee="ana")
        plumber = described("The kitchen tap drips", title="Call the plumber", due_on=today + timedelta(days=2), assignee="ana")
        photos = todo("Sort the photos")
        yield AddTodo(milk)
        yield AddTodo(plumber)
        yield AddTodo(photos)
        yield Listed(milk, plumber, photos)
        yield EditTodo(plumber.set(assignee="bo"))
        yield RemoveTodo(milk)
        yield EditTodo(photos.set(title="Sort the holiday photos"))
        yield EditTodo(plumber.set(due_on=today + timedelta(days=4)))
        yield Listed(plumber, photos)
        yield Filter(Query(assignee="ana"))
        yield Filter(Query(text="plumber"))
        yield Filter(Query(status="unscheduled"))
