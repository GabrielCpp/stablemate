from datetime import date, timedelta

from ostler.book import ApiKey, Journey, Listed

from ..endpoints import AddTodo, FindTodos, ReadTodo, RemoveTodo, UpdateTodo
from ..fixtures import Query, assigned, blank_title, past_due, scheduled, stranger, todo


class WrongTurns(Journey):
    """Ana makes the mistakes a client can make: a blank title, a date that has
    passed, a colleague who does not exist, a status nobody defined, an id nobody
    issued, no credential at all. Each is turned away with its reason and the
    list is as it was. Then she gets it right, once with the other credential."""

    def steps(self, today: date):
        rent = scheduled(today, 3, title="Pay the rent")
        yield AddTodo(rent)
        yield AddTodo(blank_title())
        yield AddTodo(past_due(today, title="Book the dentist"))
        yield AddTodo(assigned("cy", title="Book the dentist"))
        yield AddTodo(todo("Book the dentist", due_on="next tuesday"))
        yield AddTodo(todo("Book the dentist"), by=None)
        yield Listed(rent)
        yield UpdateTodo(rent.but(due_on=today - timedelta(days=30)))
        yield UpdateTodo(rent.but(title=""))
        yield ReadTodo(stranger())
        yield UpdateTodo(stranger())
        yield ReadTodo(rent, by=None)
        yield UpdateTodo(rent, by=None)
        yield RemoveTodo(rent, by=None)
        yield FindTodos(by=None)
        yield FindTodos(query=Query(status="done"))
        dentist = scheduled(today, 0, title="Book the dentist", assignee="bo")
        yield AddTodo(dentist, auth=ApiKey())
        yield Listed(dentist, rent)
