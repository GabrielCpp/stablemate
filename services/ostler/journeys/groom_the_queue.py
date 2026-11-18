from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import PathEpic, TodoAdd, TodoList, TodoPrune, TodoReorder
from ..fixtures import SECOND, path_epic, todo_add, todo_list, todo_prune, todo_reorder


class GroomTheQueue(Journey):
    """A planner shapes the order the repo works its epics. They list the queue, queue the third epic by its slug, then
    put it first, move the second ahead of the rest, drop the first, and find where the third epic and the second, named
    by its id, live. The queue lists each epic by its id."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            TodoList(todo_list()),
            TodoAdd(todo_add("third")),
            TodoList(todo_list()),
            TodoReorder(todo_reorder("third")),
            TodoList(todo_list()),
            TodoReorder(todo_reorder("0002-second", "0003-third")),
            TodoList(todo_list()),
            TodoPrune(todo_prune("first")),
            TodoList(todo_list()),
            PathEpic(path_epic("third")),
            PathEpic(path_epic(SECOND)),
            TodoAdd(todo_add("0001-first", front=True)),
            TodoList(todo_list()),
        )
