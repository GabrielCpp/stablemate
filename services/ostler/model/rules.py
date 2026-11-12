"""Why ostler says no. The message is the one it prints, word for word. A rule
reads the request (`a`) and the plan repository (`s`). ostler prints a refusal
on standard output and exits 1."""

from __future__ import annotations

from ostler.book import Actor, Exited, Rule

from ..fixtures import (EPICS, SEED_LAYERS, SEED_STATUSES, STORY_PATHS, AddArgs, ConflictArgs, PruneArgs, ReorderArgs,
                        SeedAddArgs, SeedRemoveArgs, SetStatusArgs, slug_of)
from .state import Plan

FAILED = Exited(1)


def queued_as(s: Plan, name: str | None) -> str | None:
    """The queue entry that names the same epic as this name, by the name itself or by its slug."""
    if name is None:
        return None
    epics = s.epics()
    if name in epics:
        return name
    return next((e for e in epics if slug_of(e) == slug_of(name)), None)


def _queued(a: AddArgs, s: Plan, by: Actor | None) -> bool:
    return queued_as(s, a.name) is not None


def _not_queued(a: PruneArgs, s: Plan, by: Actor | None) -> bool:
    return queued_as(s, a.name) is None


def _lost(a: ReorderArgs, s: Plan) -> tuple[str, ...]:
    return tuple(n for n in (a.first, a.then) if n is not None and queued_as(s, n) is None)


def _both_lost(a: ReorderArgs, s: Plan, by: Actor | None) -> bool:
    return len(_lost(a, s)) == 2


def _first_lost(a: ReorderArgs, s: Plan, by: Actor | None) -> bool:
    return _lost(a, s) == (a.first,)


def _then_lost(a: ReorderArgs, s: Plan, by: Actor | None) -> bool:
    return a.then is not None and _lost(a, s) == (a.then,)


def _no_epic(a: SeedAddArgs | SeedRemoveArgs, s: Plan, by: Actor | None) -> bool:
    return a.epic not in EPICS


def _bad_status(a: SeedAddArgs, s: Plan, by: Actor | None) -> bool:
    return a.status is not None and a.status not in SEED_STATUSES


def _bad_layer(a: SeedAddArgs, s: Plan, by: Actor | None) -> bool:
    return a.layer is not None and a.layer not in SEED_LAYERS


def _no_seed(a: SeedRemoveArgs, s: Plan, by: Actor | None) -> bool:
    path = f"art/epics/{a.epic}/epic.md"
    return not any(b.startswith(f"### {a.seed}\n") for b in s.files[path].holds)


def _no_story(a: SetStatusArgs | ConflictArgs, s: Plan, by: Actor | None) -> bool:
    return a.story not in STORY_PATHS


def _conflict_unclear(a: ConflictArgs, s: Plan, by: Actor | None) -> bool:
    return bool(a.text) == bool(a.clear)


already_queued = Rule[AddArgs, Plan]("epic '{canonical}' already in the queue", _queued, FAILED,
                                      why="adding an epic twice would run it twice, so the queue refuses the second.")
not_in_queue = Rule[PruneArgs, Plan]("epic '{name}' not in the queue", _not_queued, FAILED)
both_missing = Rule[ReorderArgs, Plan]("not in queue: {first}, {then}", _both_lost, FAILED)
first_missing = Rule[ReorderArgs, Plan]("not in queue: {first}", _first_lost, FAILED)
then_missing = Rule[ReorderArgs, Plan]("not in queue: {then}", _then_lost, FAILED)
no_epic_to_add_to = Rule[SeedAddArgs, Plan]("no epic '{epic}'", _no_epic, FAILED)
invalid_status = Rule[SeedAddArgs, Plan](
    "invalid status '{status}' (one of backlog, researched, covered, resolved, dropped, deferred)", _bad_status, FAILED)
invalid_layer = Rule[SeedAddArgs, Plan]("invalid layer '{layer}' (one of frontend, backend, infra)", _bad_layer, FAILED)
no_epic_to_remove_from = Rule[SeedRemoveArgs, Plan]("no epic '{epic}'", _no_epic, FAILED)
no_such_seed = Rule[SeedRemoveArgs, Plan]("no seed '{seed}' in '{epic}'", _no_seed, FAILED)
no_story_for_status = Rule[SetStatusArgs, Plan]("no story with id '{story}'", _no_story, FAILED)
conflict_unclear = Rule[ConflictArgs, Plan]("pass the conflict text, or --clear — one of the two", _conflict_unclear, FAILED)
no_story_for_conflict = Rule[ConflictArgs, Plan]("no story with id '{story}'", _no_story, FAILED)
