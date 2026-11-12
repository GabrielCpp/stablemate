"""The ostler commands the book plays: what a person types, and every way each one can end.
ostler prints its refusals on standard output and exits 1."""

from __future__ import annotations

from ostler.book import Bool, Command, Exit, Field, Files, Flag, Lines, Object, Positional, Str, Switch

from .model.actions import (AddEpic, AddSeed, ListEpics, ListFiles, PathOfEpic, PruneEpic, RecordConflict, RemoveSeed,
                            ReorderEpics, SetStoryStatus)
from .model.files import MARKS

EPIC = Field(Str(classes={"an epic with no folder": "0009-nope"}), required=False,
             does="the epic to queue: its numbered folder name, or the slug alone")
QUEUED = Field(Str(classes={"an epic the queue does not hold": "0009-nope"}), required=False,
               does="the epic to drop: its numbered folder name, or the slug alone")
SEED_EPIC = Field(Str(classes={"an epic that does not exist": "0009"}), required=False, does="the epic that lists the seed")
SEED = Field(Str(), required=False, does="the seed's id, free text")
STORY = Field(Str(classes={"a story that does not exist": "TST-NOPE"}), required=False, does="the story's id")


class TodoAdd(Command):
    does = "Queue an epic, last or first, by its folder name or its slug."
    program = "ostler"
    argv = ("--full-ids", "todo", "add", Positional("name"), Switch("--front", "front"))
    args = Object("AddArgs", name=EPIC, front=Field(Bool(), required=False, does="queue the epic first rather than last"))
    answers = (
        Exit(0, Lines(), "the epic is queued, with a warning when it has no epic.md yet"),
        Exit(1, Lines(), "the epic is already in the queue, matched by number or by slug"),
    )
    carries = AddEpic
    source = ("ostler/ostler/todo.py::add", "ostler/ostler/todo.py::_queued_as", "ostler/ostler/path.py::epic_dir_under")


class TodoPrune(Command):
    does = "Drop an epic from the queue."
    program = "ostler"
    argv = ("--full-ids", "todo", "prune", Positional("name"))
    args = Object("PruneArgs", name=QUEUED)
    answers = (
        Exit(0, Lines(), "the queued epic is dropped, named as the queue spelled it"),
        Exit(1, Lines(), "the queue does not hold the epic"),
    )
    carries = PruneEpic
    source = ("ostler/ostler/todo.py::prune",)


class TodoReorder(Command):
    does = "Move the named epics to the front of the queue in the order given; the rest keep their order after them."
    program = "ostler"
    argv = ("--full-ids", "todo", "reorder", Positional("first"), Positional("then"))
    args = Object(
        "ReorderArgs",
        first=Field(Str(classes={"an epic the queue does not hold": "0009-nope"}), required=False, does="the epic to put first"),
        then=Field(Str(classes={"an epic the queue does not hold": "0009-nope"}), required=False, does="the epic to put second"),
    )
    answers = (
        Exit(0, Lines(), "the queue is reordered"),
        Exit(1, Lines(), "the queue does not hold a named epic; the message lists those it lacks, as typed"),
    )
    carries = ReorderEpics
    source = ("ostler/ostler/todo.py::reorder",)


class TodoList(Command):
    does = "Print the queue, one epic per line, first to last."
    program = "ostler"
    argv = ("--full-ids", "todo", "list")
    args = Object("ListArgs")
    answers = (Exit(0, Lines(), "the queued epics, or (none) when the queue is empty"),)
    carries = ListEpics
    source = ("ostler/ostler/todo.py::list_epics",)


class SeedAdd(Command):
    does = "List a seed under an epic's Seeds, or replace the one that has the id."
    program = "ostler"
    argv = ("--full-ids", "seed", "add", Positional("epic"), Positional("seed"), Flag("--status", "status"), Flag("--layer", "layer"))
    args = Object(
        "SeedAddArgs",
        epic=SEED_EPIC,
        seed=SEED,
        status=Field(Str(classes={"a status the registry lacks": "weird"}), required=False,
                     does="the seed's status; backlog when left out"),
        layer=Field(Str(classes={"a layer the registry lacks": "cloud"}), required=False, does="a layer the seed touches"),
    )
    answers = (
        Exit(0, Lines(), "the seed is added, or replaced at the end of the Seeds section"),
        Exit(1, Lines(), "the epic does not exist, or the status or the layer is not one the registry lists"),
    )
    carries = AddSeed
    source = ("ostler/ostler/crud.py::add_seed", "ostler/ostler/registry.py::SEED_STATUSES", "ostler/ostler/registry.py::SEED_LAYERS")


class SeedRemove(Command):
    does = "Take a seed out of an epic's Seeds."
    program = "ostler"
    argv = ("--full-ids", "seed", "remove", Positional("epic"), Positional("seed"))
    args = Object("SeedRemoveArgs", epic=SEED_EPIC, seed=SEED)
    answers = (
        Exit(0, Lines(), "the seed is removed"),
        Exit(1, Lines(), "the epic does not exist, or it lists no seed with the id"),
    )
    carries = RemoveSeed
    source = ("ostler/ostler/crud.py::remove_seed",)


class SetStatus(Command):
    does = "Set a story's status in its frontmatter and in its Implementation Status line."
    program = "ostler"
    argv = ("--full-ids", "set-status", Positional("story"), Positional("status"))
    args = Object(
        "SetStatusArgs",
        story=STORY,
        status=Field(Str(), required=False, does="the new status, free text"),
    )
    answers = (
        Exit(0, Lines(), "the status is set"),
        Exit(1, Lines(), "no story has the id"),
    )
    carries = SetStoryStatus
    source = ("ostler/ostler/crud.py::set_status",)


class Conflict(Command):
    does = "Record the conflict found in a story's acceptance criteria, or clear it."
    program = "ostler"
    argv = ("--full-ids", "conflict", Positional("story"), Positional("text"), Switch("--clear", "clear"))
    args = Object(
        "ConflictArgs",
        story=STORY,
        text=Field(Str(), required=False, does="the conflict and the chain that found it; left out with --clear"),
        clear=Field(Bool(), required=False, does="remove the recorded conflict"),
    )
    answers = (
        Exit(0, Lines(), "the conflict is recorded or cleared"),
        Exit(1, Lines(), "the text and --clear are both given or both left out, or no story has the id"),
    )
    carries = RecordConflict
    source = ("ostler/ostler/cli.py::main", "ostler/ostler/crud.py::set_conflict")


class PathEpic(Command):
    does = "Print where an epic lives, relative to the repository."
    program = "ostler"
    argv = ("--full-ids", "path", "epic", Positional("name"))
    args = Object("PathEpicArgs", name=Field(Str(classes={"an epic with no folder": "nope"}), required=False, does="the epic, by number or slug"))
    answers = (Exit(0, Lines(), "the epic's folder, whether or not it exists"),)
    carries = PathOfEpic
    source = ("ostler/ostler/path.py::epic_dir_under",)


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("ostler/ostler/crud.py::set_status", "ostler/ostler/crud.py::add_seed")


ALL = (TodoAdd, TodoPrune, TodoReorder, TodoList, SeedAdd, SeedRemove, SetStatus, Conflict, PathEpic, Look)
