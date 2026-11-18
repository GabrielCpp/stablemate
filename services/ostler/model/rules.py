"""Why ostler says no. The message is the one it prints, word for word. A rule
reads the request (`a`) and the plan repository (`s`). ostler prints a refusal
on standard output and exits 1."""

from __future__ import annotations

from ostler.book import Actor, Exited, Rule

from ..fixtures import (SEED_LAYERS, SEED_STATUSES, AddArgs, ListArgs, ConflictArgs, CreateEpicArgs, CreateStoryArgs,
                        DeleteStoryArgs, PathBranchArgs, PathSpecArgs, PathStoryArgs, PruneArgs, ReorderArgs, SeedAddArgs,
                        SeedRemoveArgs, SetStatusArgs, UnblockArgs, UpdateStoryArgs)
from .state import Plan

FAILED = Exited(1)


def queued_as(s: Plan, name: str | None) -> str | None:
    """The queue entry that names the same epic as this name: the entry spelled as typed, else the first entry that
    stands for the epic the name stands for. A name that stands for no epic matches only itself."""
    if name is None:
        return None
    epics = s.epics()
    if name in epics:
        return name
    wanted = s.epic_of(name)
    if wanted is None:
        return None
    return next((e for e in epics if s.epic_of(e) == wanted), None)


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


def _twice(a: ReorderArgs, s: Plan, by: Actor | None) -> bool:
    return a.first is not None and a.then is not None and queued_as(s, a.first) == queued_as(s, a.then)


def _no_epic(a: SeedAddArgs | SeedRemoveArgs, s: Plan, by: Actor | None) -> bool:
    return s.epic_of(a.epic) is None


def _bad_status(a: SeedAddArgs, s: Plan, by: Actor | None) -> bool:
    return a.status is not None and a.status not in SEED_STATUSES


def _bad_layer(a: SeedAddArgs, s: Plan, by: Actor | None) -> bool:
    return a.layer is not None and a.layer not in SEED_LAYERS


def _no_seed(a: SeedRemoveArgs, s: Plan, by: Actor | None) -> bool:
    path = f"art/epics/{s.resolve_epic(a.epic)}/epic.md"
    return not any(b.startswith(f"### {a.seed}\n") for b in s.files[path].holds)


def _no_story(a: SetStatusArgs | ConflictArgs | DeleteStoryArgs | UpdateStoryArgs | PathStoryArgs | PathSpecArgs | UnblockArgs,
              s: Plan, by: Actor | None) -> bool:
    return not s.has_story(a.story or "")


def _epic_present(s: Plan, name: str | None) -> bool:
    return s.epic_of(name) is not None


def _epic_exists(a: CreateEpicArgs, s: Plan, by: Actor | None) -> bool:
    return _epic_present(s, a.slug)


def _no_epic_for_story(a: CreateStoryArgs, s: Plan, by: Actor | None) -> bool:
    return not _epic_present(s, a.epic)


def _nothing_named(a: UnblockArgs, s: Plan, by: Actor | None) -> bool:
    return not (a.story or a.epic or a.all)


def _all_with_target(a: UnblockArgs, s: Plan, by: Actor | None) -> bool:
    return bool(a.all and (a.story or a.epic))


def _both_named(a: UnblockArgs, s: Plan, by: Actor | None) -> bool:
    return bool(a.story and a.epic)


def _unblock_no_story(a: UnblockArgs, s: Plan, by: Actor | None) -> bool:
    return bool(a.story) and not s.has_story(a.story or "")


def _unblock_no_epic(a: UnblockArgs, s: Plan, by: Actor | None) -> bool:
    return not a.story and bool(a.epic) and not _epic_present(s, a.epic)


def _no_branch_story(a: PathBranchArgs, s: Plan, by: Actor | None) -> bool:
    return not a.epic and not s.has_story(a.ref or "")


def _empty_status(a: SetStatusArgs, s: Plan, by: Actor | None) -> bool:
    return a.trimmed == ""


def _conflict_unclear(a: ConflictArgs, s: Plan, by: Actor | None) -> bool:
    return bool(a.text) == bool(a.clear)


already_queued = Rule[AddArgs, Plan]("epic '{canonical}' already in the queue", _queued, FAILED,
                                      why="adding an epic twice would run it twice, so the queue refuses the second.")
not_in_queue = Rule[PruneArgs, Plan]("epic '{name}' not in the queue", _not_queued, FAILED)
both_missing = Rule[ReorderArgs, Plan]("not in queue: {first}, {then}", _both_lost, FAILED)
first_missing = Rule[ReorderArgs, Plan]("not in queue: {first}", _first_lost, FAILED)
then_missing = Rule[ReorderArgs, Plan]("not in queue: {then}", _then_lost, FAILED)
named_twice = Rule[ReorderArgs, Plan](
    "epic '{repeated}' named more than once", _twice, FAILED,
    why="a repeated name is most often a typo for another epic, so the reorder says which name repeats and writes "
        "nothing, where dropping the repeat would reorder the queue on a guess.")
no_epic_to_add_to = Rule[SeedAddArgs, Plan]("no epic '{epic}'", _no_epic, FAILED)
invalid_status = Rule[SeedAddArgs, Plan](
    "invalid status '{status}' (one of backlog, researched, covered, resolved, dropped, deferred)", _bad_status, FAILED)
invalid_layer = Rule[SeedAddArgs, Plan]("invalid layer '{layer}' (one of frontend, backend, infra)", _bad_layer, FAILED)
no_epic_to_remove_from = Rule[SeedRemoveArgs, Plan]("no epic '{epic}'", _no_epic, FAILED)
no_such_seed = Rule[SeedRemoveArgs, Plan]("no seed '{seed}' in '{epic}'", _no_seed, FAILED)
no_story_for_status = Rule[SetStatusArgs, Plan]("no story with id '{story}'", _no_story, FAILED)
empty_status = Rule[SetStatusArgs, Plan](
    "status of '{story}' cannot be empty", _empty_status, FAILED,
    why="a script that passes an unset variable would blank the story's status and be told it worked.")
conflict_unclear = Rule[ConflictArgs, Plan]("pass the conflict text, or --clear — one of the two", _conflict_unclear, FAILED)
no_story_for_conflict = Rule[ConflictArgs, Plan]("no story with id '{story}'", _no_story, FAILED)
epic_exists = Rule[CreateEpicArgs, Plan](
    "epic '{slug}' already exists ({canonical})", _epic_exists, FAILED,
    why="two epics with one slug would leave a command that names the slug unable to tell which epic it means.")
no_epic_for_story = Rule[CreateStoryArgs, Plan]("no epic '{epic}'", _no_epic_for_story, FAILED)
no_story_to_delete = Rule[DeleteStoryArgs, Plan]("no story with id '{story}'", _no_story, FAILED)
no_story_to_update = Rule[UpdateStoryArgs, Plan]("no story with id '{story}'", _no_story, FAILED)
nothing_to_unblock_named = Rule[UnblockArgs, Plan]("name a story, pass --epic, or pass --all", _nothing_named, FAILED)
all_takes_no_target = Rule[UnblockArgs, Plan]("--all takes no story or --epic", _all_with_target, FAILED)
story_and_epic = Rule[UnblockArgs, Plan]("pass a story or an epic, not both", _both_named, FAILED)
unblock_no_story = Rule[UnblockArgs, Plan]("no story with id '{story}'", _unblock_no_story, FAILED)
unblock_no_epic = Rule[UnblockArgs, Plan]("no epic '{epic}'", _unblock_no_epic, FAILED)
no_story_for_story_path = Rule[PathStoryArgs, Plan]("error: no story with id '{story}'", _no_story, FAILED)
no_story_for_spec_path = Rule[PathSpecArgs, Plan]("error: no story with id '{story}'", _no_story, FAILED)
no_story_for_branch = Rule[PathBranchArgs, Plan]("error: no story with id '{ref}'", _no_branch_story, FAILED)


def _numbered(a: object, s: Plan, by: Actor | None) -> bool:
    return bool(s.numbered())


shelf_numbered = Rule[ListArgs, Plan](
    "error: the epics shelf <sandbox>/art/epics still names 1 epic folder(s) by number and slug (0004-legacy); epic and "
    "story folders are named by their ids now. Run `ostler layout apply` to rename them, record each epic's slug and "
    "repoint the queue, then run ostler again", _numbered, FAILED,
    why="a command that read a numbered folder would build every path, queue entry and milestone line from a name "
        "that goes stale, so ostler reads nothing until the shelf is renamed.")
