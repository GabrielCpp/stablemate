from datetime import date, timedelta

from ostler.book import Journey, Listed, Relates, Same

from ..endpoints import AddTodo, FindTodos, ReadTodo, RemoveTodo, UpdateTodo
from ..fixtures import Query, scheduled, todo


class AWeekOfChores(Journey):
    """Ana plans her week. She writes down three chores, one with no date yet,
    hands one to Bo, finishes one and crosses it off, renames another, and moves
    the first one's due date back a day. Then she looks at what is left for her."""

    def steps(self, today: date):
        milk = scheduled(today, 1, title="Buy milk", assignee="ana")
        plumber = scheduled(today, 2, title="Call the plumber", description="The kitchen tap drips", assignee="ana")
        photos = todo("Sort the photos")
        yield AddTodo(milk)
        yield AddTodo(plumber)
        yield AddTodo(photos)
        yield Listed(milk, plumber, photos)
        yield UpdateTodo(plumber.set(assignee="bo"))
        yield RemoveTodo(milk)
        yield UpdateTodo(photos.set(title="Sort the holiday photos"))
        yield UpdateTodo(plumber.set(due_on=today + timedelta(days=4)))
        yield Listed(plumber, photos)
        yield ReadTodo(plumber)
        yield FindTodos(query=Query(assignee="ana"))
        yield FindTodos(query=Query(text="plumber"))
        yield FindTodos(query=Query(status="unscheduled"))
        first, again = FindTodos(), FindTodos()
        yield first
        yield again
        yield Same(first, again)
        one = ReadTodo(plumber)
        yield one
        yield Relates("the todo read back is the todo listed", (one, first), lambda read, found: None if read.body["title"] in [t["title"] for t in found.body] else f"{read.body['title']} is not in the list")
