"""The lifecycle matrices of a plan repository: how far the queue, a story and an
epic's seeds have come, and what each command does to them there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from ..commands import (Conflict, Look, PathEpic, SeedAdd, SeedRemove, SetStatus, TodoAdd, TodoList, TodoPrune,
                        TodoReorder)
from ..fixtures import (ALPHA, conflict, path_epic, seed_add, seed_remove, set_status, todo_add, todo_list,
                        todo_prune, todo_reorder)
from .state import Plan, queue_stage, seed_stage, story_stage

TODAY = date(2026, 11, 12)

QUEUE_SCENES = (
    Scene("first > second", "the queue holds the two epics it starts with", lambda today: ()),
    Scene("first > second > third", "the third epic is queued last", lambda today: (TodoAdd(todo_add("third")),)),
    Scene("third > first > second", "the third epic is queued first", lambda today: (TodoAdd(todo_add("0003-third", front=True)),)),
    Scene("second > first", "the second epic was moved ahead of the first",
          lambda today: (TodoReorder(todo_reorder("0002-second")),)),
    Scene("empty", "both epics were pruned",
          lambda today: (TodoPrune(todo_prune("0001-first")), TodoPrune(todo_prune("0002-second")))),
)

QUEUE_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "add": lambda m: TodoAdd(todo_add("third")),
    "add by number": lambda m: TodoAdd(todo_add("0003-third")),
    "add to the front": lambda m: TodoAdd(todo_add("third", front=True)),
    "add a queued epic": lambda m: TodoAdd(todo_add("second")),
    "add an epic with no folder": lambda m: TodoAdd(todo_add("0009-nope")),
    "prune": lambda m: TodoPrune(todo_prune("second")),
    "prune an unqueued epic": lambda m: TodoPrune(todo_prune("0003-third")),
    "reorder one": lambda m: TodoReorder(todo_reorder("second")),
    "reorder two": lambda m: TodoReorder(todo_reorder("0002-second", "0001-first")),
    "reorder an unqueued epic": lambda m: TodoReorder(todo_reorder("0001-first", "0003-third")),
    "reorder two unqueued epics": lambda m: TodoReorder(todo_reorder("0003-third", "0009-nope")),
    "reorder a repeated epic": lambda m: TodoReorder(todo_reorder("0002-second", "0002-second")),
    "reorder a repeated epic by its slug and its number": lambda m: TodoReorder(todo_reorder("second", "0002-second")),
    "reorder a repeated epic by its number and its slug": lambda m: TodoReorder(todo_reorder("0001-first", "first")),
    "reorder a repeated third epic": lambda m: TodoReorder(todo_reorder("0003-third", "0003-third")),
    "reorder a repeated epic with no folder": lambda m: TodoReorder(todo_reorder("0009-nope", "0009-nope")),
    "list": lambda m: TodoList(todo_list()),
    "path of an epic by number": lambda m: PathEpic(path_epic("0001-first")),
    "path of an epic by slug": lambda m: PathEpic(path_epic("first")),
    "path of an epic with no folder": lambda m: PathEpic(path_epic("nope")),
}

STORY_SCENES = (
    Scene("Not started", "the story has not begun", lambda today: ()),
    Scene("in-progress", "the story is in progress", lambda today: (SetStatus(set_status(ALPHA, "in-progress")),)),
    Scene("Blocked: waiting", "the story is blocked",
          lambda today: (SetStatus(set_status(ALPHA, "Blocked: waiting")),)),
    Scene("Done", "the story is done", lambda today: (SetStatus(set_status(ALPHA, "Done")),)),
    Scene("Not started with conflict", "a conflict is recorded on the story",
          lambda today: (Conflict(conflict(ALPHA, "criteria disagree")),)),
    Scene("in-progress with conflict", "the story is in progress and a conflict is recorded",
          lambda today: (SetStatus(set_status(ALPHA, "in-progress")), Conflict(conflict(ALPHA, "criteria disagree")))),
)

STORY_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "set in-progress": lambda m: SetStatus(set_status(ALPHA, "in-progress")),
    "set Blocked: waiting": lambda m: SetStatus(set_status(ALPHA, "Blocked: waiting")),
    "set Not started": lambda m: SetStatus(set_status(ALPHA, "Not started")),
    "set In progress": lambda m: SetStatus(set_status(ALPHA, "In progress")),
    "set Done": lambda m: SetStatus(set_status(ALPHA, "Done")),
    "set a status with spaces around it": lambda m: SetStatus(set_status(ALPHA, " Done ")),
    "set an empty status": lambda m: SetStatus(set_status(ALPHA, "")),
    "set a status with tabs around it": lambda m: SetStatus(set_status(ALPHA, "\tDone\t")),
    "set a status of spaces": lambda m: SetStatus(set_status(ALPHA, "   ")),
    "set a status of a tab": lambda m: SetStatus(set_status(ALPHA, "\t")),
    "set status of an unknown story": lambda m: SetStatus(set_status("TST-NOPE", "in-progress")),
    "set an empty status on an unknown story": lambda m: SetStatus(set_status("TST-NOPE", "")),
    "record a conflict": lambda m: Conflict(conflict(ALPHA, "criteria disagree")),
    "replace the conflict": lambda m: Conflict(conflict(ALPHA, "specs contradict")),
    "clear the conflict": lambda m: Conflict(conflict(ALPHA, None, clear=True)),
    "conflict with neither text nor clear": lambda m: Conflict(conflict(ALPHA, None)),
    "conflict with both text and clear": lambda m: Conflict(conflict(ALPHA, "criteria disagree", clear=True)),
    "conflict on an unknown story": lambda m: Conflict(conflict("TST-NOPE", "criteria disagree")),
    "look": lambda m: Look(),
}

SEED_SCENES = (
    Scene("no seeds", "the epic lists no seeds", lambda today: ()),
    Scene("SD-3", "the epic lists the seed SD-3", lambda today: (SeedAdd(seed_add("0002-second", "SD-3")),)),
    Scene("SD-3 + SD-4", "the epic lists the seeds SD-3 and SD-4",
          lambda today: (SeedAdd(seed_add("0002-second", "SD-3")), SeedAdd(seed_add("0002-second", "SD-4", status="researched", layer="frontend")))),
)

SEED_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "add": lambda m: SeedAdd(seed_add("0002-second", "SD-3")),
    "add with a status": lambda m: SeedAdd(seed_add("0002-second", "SD-3", status="researched")),
    "add with a layer": lambda m: SeedAdd(seed_add("0002-second", "SD-4", layer="frontend")),
    "add with a status and a layer": lambda m: SeedAdd(seed_add("0002-second", "SD-4", status="researched", layer="frontend")),
    "add to an unknown epic": lambda m: SeedAdd(seed_add("0009", "SD-3")),
    "add with an invalid status": lambda m: SeedAdd(seed_add("0002-second", "SD-3", status="weird")),
    "add with an invalid layer": lambda m: SeedAdd(seed_add("0002-second", "SD-3", layer="cloud")),
    "remove": lambda m: SeedRemove(seed_remove("0002-second", "SD-3")),
    "remove the second seed": lambda m: SeedRemove(seed_remove("0002-second", "SD-4")),
    "remove from an unknown epic": lambda m: SeedRemove(seed_remove("0009", "SD-3")),
    "look": lambda m: Look(),
}


MATRICES = (
    Axes[Plan]("queue", TODAY, QUEUE_SCENES, QUEUE_ACTIONS, queue_stage, state_of=lambda m, _: queue_stage(m)),
    Axes[Plan]("story", TODAY, STORY_SCENES, STORY_ACTIONS, story_stage, state_of=lambda m, _: story_stage(m)),
    Axes[Plan]("seeds", TODAY, SEED_SCENES, SEED_ACTIONS, seed_stage, state_of=lambda m, _: seed_stage(m)),
)
