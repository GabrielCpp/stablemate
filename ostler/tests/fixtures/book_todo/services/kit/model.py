"""What the kit app keeps: the todos a user added. It lists none of them, so no row is ever shown."""

from __future__ import annotations

from uuid import uuid4

from ostler.book import Action, Actor, Collection, State, Transaction, Create, Unique

from ..web.model.actions import record
from ..web.model.rules import title_required, title_too_long
from ..web.model.todo import TodoRecord
from .fixtures import Todo, Who


class KitApp(State):
    todos = Collection(TodoRecord, Unique("id"))

    def rows(self) -> tuple[object, ...]:
        return ()

    def row(self, entity: object) -> object:
        return ()


class Add(Action[Todo, KitApp]):
    accept = Todo
    rules = (title_required, title_too_long)

    @staticmethod
    def reduce(a: Todo, s: KitApp, by: Actor | None) -> Transaction:
        a.set(id=str(uuid4()))
        return Transaction(Create(s.todos, record(a)))


class Choose(Action[Who, KitApp]):
    accept = Who
