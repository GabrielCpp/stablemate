from __future__ import annotations

from datetime import date
from typing import Iterable

from ostler.book import Journey

from ..commands import Conflict, SeedAdd, SeedRemove, SetStatus, TodoAdd, TodoList, TodoPrune, TodoReorder
from ..fixtures import ALPHA, conflict, seed_add, seed_remove, set_status, todo_add, todo_list, todo_prune, todo_reorder


class WrongTurns(Journey):
    """A planner slips. They queue an epic twice, prune and reorder epics the queue lacks, name an epic twice in a
    reorder, once by the same name and once by its slug and its number, queue an epic that has no folder yet, list a
    seed with a status and a layer the registry lacks, remove a seed that is not there, give a story an empty status
    or one made of spaces and tabs and then `In progress`, and name a story that does not exist or give a conflict
    no text."""

    alone = True

    def steps(self, today: date) -> Iterable[object]:
        return (
            TodoAdd(todo_add("second")),
            TodoPrune(todo_prune("0003-third")),
            TodoReorder(todo_reorder("0003-third", "0001-first")),
            TodoReorder(todo_reorder("0002-second", "0002-second")),
            TodoReorder(todo_reorder("first", "0001-first")),
            TodoReorder(todo_reorder("0009-nope", "0009-nope")),
            TodoList(todo_list()),
            TodoAdd(todo_add("0009-nope")),
            TodoReorder(todo_reorder("0009-nope", "0002-second")),
            SeedAdd(seed_add("0009", "SD-3")),
            SeedAdd(seed_add("0002-second", "SD-3", status="weird")),
            SeedAdd(seed_add("0002-second", "SD-3", layer="cloud")),
            SeedRemove(seed_remove("0002-second", "SD-3")),
            SetStatus(set_status(ALPHA, "")),
            SetStatus(set_status(ALPHA, "  \t ")),
            SetStatus(set_status("TST-NOPE", "")),
            SetStatus(set_status(ALPHA, "In progress")),
            SetStatus(set_status("TST-NOPE", "in-progress")),
            Conflict(conflict(ALPHA, None)),
            Conflict(conflict(ALPHA, "criteria disagree", clear=True)),
            Conflict(conflict("TST-NOPE", "criteria disagree")),
        )
