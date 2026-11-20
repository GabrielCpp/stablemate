"""What each command does to the plan repository and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Delete, Select, Transaction, Update

from ..fixtures import (COVERS, SLUGS, STORY_PATHS, ConflictArgs, CreateEpicArgs, CreateStoryArgs,
                        DeleteEpicArgs, DeleteStoryArgs, Nothing, PathBranchArgs, PathEpicArgs, PathSpecArgs, PathStoryArgs,
                        SeedAddArgs, SeedRemoveArgs, SetStatusArgs, UnblockArgs, UpdateStoryArgs,
                        slug_of)
from . import rules
from .files import (BULLET_LINES, CONFLICT_LINES, LEGACY, LEGACY_SLUG, LEGACY_STORY, MOVED_EPIC, MOVED_STORY, NOT_STARTED,
                    OLD_EPIC, OLD_FOLDER, OLD_STORY, RECORDED_SLUG, STATUS_LINES, FileRecord, holding, seed_block)
from .records import MintedEpic, MintedStory
from .state import MINTED, Plan


def rewrite(s: Plan, path: str, *strings: str) -> Update:
    """The change that leaves this file holding exactly these strings."""
    return Update(s.files, path, holding(path, *strings))


class AddSeed(Action[SeedAddArgs, Plan]):
    accept = SeedAddArgs
    rules = (rules.no_epic_to_add_to, rules.invalid_status, rules.invalid_layer)

    @staticmethod
    def reduce(a: SeedAddArgs, s: Plan, by: Actor | None) -> Transaction:
        path = f"art/epics/{s.resolve_epic(a.epic)}/epic.md"
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
        path = f"art/epics/{s.resolve_epic(a.epic)}/epic.md"
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
    rules = (rules.shelf_numbered,)

    @staticmethod
    def reduce(a: PathEpicArgs, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=(f"art/epics/{s.resolve_epic(a.name)}",))


class ListFiles(Action[object, Plan]):
    @staticmethod
    def reduce(a: object, s: Plan, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: tuple(f.path.split("/")))


def status_of(s: Plan, path: str) -> str:
    held = s.files[path].holds
    return next(name for name, line in STATUS_LINES.items() if line in held)


def with_status(s: Plan, story: str, status: str) -> Update:
    path = STORY_PATHS[story]
    replaced = (*STATUS_LINES.values(), *BULLET_LINES.values())
    kept = tuple(h for h in s.files[path].holds if h not in replaced)
    return rewrite(s, path, *kept, STATUS_LINES[status], BULLET_LINES[status])


def epic_of(path: str) -> str:
    return path.split("/")[2]


class MakeEpic(Action[CreateEpicArgs, Plan]):
    accept = CreateEpicArgs
    rules = (rules.epic_exists,)

    @staticmethod
    def reduce(a: CreateEpicArgs, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(Create(s.minted, MintedEpic(a.slug, a.title or "")), says=())


class MakeStory(Action[CreateStoryArgs, Plan]):
    accept = CreateStoryArgs
    rules = (rules.no_epic_for_story,)

    @staticmethod
    def reduce(a: CreateStoryArgs, s: Plan, by: Actor | None) -> Transaction:
        folder = s.resolve_epic(a.epic)
        slug = a.slug or ""
        if slug in s.stories_of(folder):
            return Transaction(says=(f"story '{slug}' already exists in epic '{a.epic}'",))
        made = Create(s.stories, MintedStory(f"{folder}/{slug}", folder, slug))
        epic_path = f"art/epics/{folder}/epic.md"
        if epic_path not in s.files.items:
            return Transaction(made, says=())
        held = s.files[epic_path].holds
        return Transaction(made, rewrite(s, epic_path, *held, f"### {slug}", f"- title: {a.title}"), says=())


class DropEpic(Action[DeleteEpicArgs, Plan]):
    accept = DeleteEpicArgs

    @staticmethod
    def reduce(a: DeleteEpicArgs, s: Plan, by: Actor | None) -> Transaction:
        name = a.name or ""
        folder = s.resolve_epic(name)
        existed = folder in s.folders()
        gone = tuple(f.path for f in s.files if f.path.startswith("art/epics/") and epic_of(f.path) == folder)
        changes: list = [Delete(s.files, path) for path in gone]
        changes += [Delete(s.stories, story.key) for story in s.stories if story.epic == folder]
        changes += [Delete(s.minted, epic.slug) for epic in s.minted if MINTED.format(epic.slug) == folder]
        if folder.startswith(MINTED.format("")[:-1]):
            return Transaction(*changes, says=())
        if not existed:
            return Transaction(*changes, says=(f"epic '{name}' already absent; cleanup complete",))
        return Transaction(*changes, says=(f"deleted epic '{folder}'",))


class DropStory(Action[DeleteStoryArgs, Plan]):
    accept = DeleteStoryArgs
    rules = (rules.no_story_to_delete,)

    @staticmethod
    def reduce(a: DeleteStoryArgs, s: Plan, by: Actor | None) -> Transaction:
        assert a.story is not None
        path = STORY_PATHS[a.story]
        slug = SLUGS[a.story]
        epic_path = f"art/epics/{epic_of(path)}/epic.md"
        dropped = (f"### {slug}", f"- title: Story {slug}", f"- title: Renamed {slug}", f"- covers: {COVERS[a.story]}")
        kept = tuple(h for h in s.files[epic_path].holds if h not in dropped)
        return Transaction(Delete(s.files, path), rewrite(s, epic_path, *kept),
                           says=(f"deleted story '{slug}' from epic '{epic_of(path)}'",))


class EditStory(Action[UpdateStoryArgs, Plan]):
    accept = UpdateStoryArgs
    rules = (rules.no_story_to_update,)

    @staticmethod
    def reduce(a: UpdateStoryArgs, s: Plan, by: Actor | None) -> Transaction:
        assert a.story is not None
        path = STORY_PATHS[a.story]
        slug = SLUGS[a.story]
        epic_path = f"art/epics/{epic_of(path)}/epic.md"
        titles = (f"- title: Story {slug}", f"- title: Renamed {slug}")
        kept = tuple(h for h in s.files[epic_path].holds if h not in titles and h != f"- covers: {COVERS[a.story]}")
        cover = () if a.covers == "(none)" else (f"- covers: {a.covers}",)
        blocker = () if a.depends == "(none)" else (f"- Blocked by: {a.depends}",)
        story_kept = tuple(h for h in s.files[path].holds if not h.startswith("- Blocked by: "))
        return Transaction(rewrite(s, epic_path, *kept, f"- title: {a.title}", *cover), rewrite(s, path, *story_kept, *blocker),
                           says=(f"updated story '{slug}' in epic '{epic_of(path)}'",))


class ClearBlocks(Action[UnblockArgs, Plan]):
    accept = UnblockArgs
    rules = (rules.nothing_to_unblock_named, rules.all_takes_no_target, rules.story_and_epic, rules.unblock_no_story,
             rules.unblock_no_epic)

    @staticmethod
    def reduce(a: UnblockArgs, s: Plan, by: Actor | None) -> Transaction:
        if a.story:
            candidates = [a.story]
        elif a.epic:
            folder = s.epic_of(a.epic)
            candidates = [sid for sid, path in sorted(STORY_PATHS.items(), key=lambda kv: kv[1])
                          if epic_of(path) == folder and s.has_story(sid)]
        else:
            candidates = [sid for sid, path in sorted(STORY_PATHS.items(), key=lambda kv: kv[1]) if s.has_story(sid)]
        blocked = [sid for sid in candidates if status_of(s, STORY_PATHS[sid]).lower().startswith("blocked")]
        if not blocked:
            tail = f": '{a.target}' is not blocked" if a.target else ""
            return Transaction(says=(f"nothing to unblock{tail}",))
        status = (a.status or "Not started").strip()
        names = ", ".join(SLUGS[sid] for sid in blocked)
        return Transaction(*(with_status(s, sid, status) for sid in blocked),
                           says=(f"unblocked {len(blocked)} → {a.status or 'Not started'}: {names}",))


class StoryPath(Action[PathStoryArgs, Plan]):
    accept = PathStoryArgs
    rules = (rules.no_story_for_story_path,)

    @staticmethod
    def reduce(a: PathStoryArgs, s: Plan, by: Actor | None) -> Transaction:
        assert a.story is not None
        return Transaction(says=(STORY_PATHS[a.story],))


class SpecPath(Action[PathSpecArgs, Plan]):
    accept = PathSpecArgs
    rules = (rules.no_story_for_spec_path,)

    @staticmethod
    def reduce(a: PathSpecArgs, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=(f"<sandbox>/art/specs/{a.story}",))


class BranchName(Action[PathBranchArgs, Plan]):
    accept = PathBranchArgs
    rules = (rules.no_story_for_branch,)

    @staticmethod
    def reduce(a: PathBranchArgs, s: Plan, by: Actor | None) -> Transaction:
        ref = a.ref or ""
        if a.epic:
            folder = s.epic_of(ref)
            return Transaction(says=(f"feat/{s.folders()[folder] if folder else slug_of(ref)}",))
        return Transaction(says=(SLUGS[ref],))


class CopyOldEpic(Action[object, Plan]):
    @staticmethod
    def reduce(a: object, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(Create(s.files, holding(OLD_EPIC)), Create(s.files, holding(OLD_STORY, NOT_STARTED)))


class ApplyLayout(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        if OLD_EPIC not in s.files.items:
            return Transaction(says=("every epic and story folder is already named by its id",))
        changes: list = [Delete(s.files, OLD_EPIC), Delete(s.files, OLD_STORY), Create(s.files, holding(MOVED_EPIC, RECORDED_SLUG)),
                         Create(s.files, holding(MOVED_STORY, NOT_STARTED))]
        says = (f"{OLD_FOLDER}: recorded slug `{LEGACY_SLUG}`", f"{OLD_FOLDER}/stories/echo -> {LEGACY_STORY}",
                f"{OLD_FOLDER} -> {LEGACY}")
        return Transaction(*changes, says=says)
