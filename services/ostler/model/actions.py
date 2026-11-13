"""What each command does to the plan repository and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Select, Transaction, Update

from ..fixtures import (EPICS, STORY_PATHS, AddArgs, ConflictArgs, ListArgs, PathEpicArgs, PruneArgs, ReorderArgs, SeedAddArgs,
                        SeedRemoveArgs, SetStatusArgs, directory_of)
from . import rules
from .files import BULLET_LINES, CONFLICT_LINES, STATUS_LINES, FileRecord, holding, seed_block
from .records import Queue
from .rules import queued_as
from .state import QUEUE, Plan

WARNING = " — WARNING: no '{name}/epic.md' yet, so epic selection will skip it and report no work remaining"


def requeue(s: Plan, epics: tuple[str, ...]) -> Update:
    return Update(s.queue, QUEUE, Queue(QUEUE, epics))


def rewrite(s: Plan, path: str, *strings: str) -> Update:
    """The change that leaves this file holding exactly these strings."""
    return Update(s.files, path, holding(path, *strings))


class AddEpic(Action[AddArgs, Plan]):
    accept = AddArgs
    rules = (rules.already_queued,)

    @staticmethod
    def reduce(a: AddArgs, s: Plan, by: Actor | None) -> Transaction:
        name = a.canonical
        epics = (name, *s.epics()) if a.front else (*s.epics(), name)
        warning = "" if name in EPICS else WARNING.format(name=name)
        return Transaction(requeue(s, epics), says=(f"queued epic '{name}'{warning}",))


class PruneEpic(Action[PruneArgs, Plan]):
    accept = PruneArgs
    rules = (rules.not_in_queue,)

    @staticmethod
    def reduce(a: PruneArgs, s: Plan, by: Actor | None) -> Transaction:
        queued = queued_as(s, a.name)
        epics = tuple(e for e in s.epics() if e != queued)
        return Transaction(requeue(s, epics), says=(f"pruned epic '{queued}' from the queue",))


class ReorderEpics(Action[ReorderArgs, Plan]):
    accept = ReorderArgs
    rules = (rules.both_missing, rules.first_missing, rules.then_missing, rules.named_twice)

    @staticmethod
    def reduce(a: ReorderArgs, s: Plan, by: Actor | None) -> Transaction:
        named = [queued_as(s, n) for n in (a.first, a.then) if n is not None]
        front = tuple(n for n in named if n is not None)
        epics = (*front, *(e for e in s.epics() if e not in front))
        return Transaction(requeue(s, epics), says=("reordered epics queue",))


class ListEpics(Action[ListArgs, Plan]):
    accept = ListArgs

    @staticmethod
    def reduce(a: ListArgs, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=s.epics() or ("(none)",))


class AddSeed(Action[SeedAddArgs, Plan]):
    accept = SeedAddArgs
    rules = (rules.no_epic_to_add_to, rules.invalid_status, rules.invalid_layer)

    @staticmethod
    def reduce(a: SeedAddArgs, s: Plan, by: Actor | None) -> Transaction:
        path = f"art/epics/{a.epic}/epic.md"
        assert a.seed is not None
        held = s.files[path].holds
        existed = any(b.startswith(f"### {a.seed}\n") for b in held)
        kept = tuple(b for b in held if not b.startswith(f"### {a.seed}\n"))
        block = seed_block(a.seed, a.status or "backlog", a.layer)
        verb = "updated" if existed else "added"
        return Transaction(rewrite(s, path, *kept, block), says=(f"{verb} seed '{a.seed}' in epic '{a.epic}'",))


class RemoveSeed(Action[SeedRemoveArgs, Plan]):
    accept = SeedRemoveArgs
    rules = (rules.no_epic_to_remove_from, rules.no_such_seed)

    @staticmethod
    def reduce(a: SeedRemoveArgs, s: Plan, by: Actor | None) -> Transaction:
        path = f"art/epics/{a.epic}/epic.md"
        kept = tuple(b for b in s.files[path].holds if not b.startswith(f"### {a.seed}\n"))
        return Transaction(rewrite(s, path, *kept), says=(f"removed seed '{a.seed}' from epic '{a.epic}'",))


class SetStoryStatus(Action[SetStatusArgs, Plan]):
    accept = SetStatusArgs
    rules = (rules.no_story_for_status, rules.empty_status)

    @staticmethod
    def reduce(a: SetStatusArgs, s: Plan, by: Actor | None) -> Transaction:
        assert a.story is not None
        status = a.trimmed
        path = STORY_PATHS[a.story]
        replaced = (*STATUS_LINES.values(), *BULLET_LINES.values())
        kept = tuple(h for h in s.files[path].holds if h not in replaced)
        return Transaction(rewrite(s, path, *kept, STATUS_LINES[status], BULLET_LINES[status]),
                           says=(f"status of '{a.story}' → {status}",))


class RecordConflict(Action[ConflictArgs, Plan]):
    accept = ConflictArgs
    rules = (rules.conflict_unclear, rules.no_story_for_conflict)

    @staticmethod
    def reduce(a: ConflictArgs, s: Plan, by: Actor | None) -> Transaction:
        assert a.story is not None
        path = STORY_PATHS[a.story]
        kept = tuple(h for h in s.files[path].holds if h not in CONFLICT_LINES)
        if a.clear:
            return Transaction(rewrite(s, path, *kept), says=(f"conflict cleared off '{a.story}'",))
        return Transaction(rewrite(s, path, *kept, f"conflict: {a.text}"), says=(f"conflict recorded on '{a.story}'",))


class PathOfEpic(Action[PathEpicArgs, Plan]):
    accept = PathEpicArgs

    @staticmethod
    def reduce(a: PathEpicArgs, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=(f"art/epics/{directory_of(a.name or '')}",))


class ListFiles(Action[object, Plan]):
    @staticmethod
    def reduce(a: object, s: Plan, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: f.path)
