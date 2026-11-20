"""What a user types after the command name, as the model reads it. A field is
named as the argument is, and left None where the user leaves the flag out."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from ostler.book import Actor, Fixture

FIRST = "TST-01M585P778TKS9VRC0053BQDSZ"
SECOND = "TST-01M585PEGMRE3FWETV74QRSSY3"
THIRD = "TST-01M585PF6G57AQ3V1JZA5X8PKY"
SLUG_OF = {FIRST: "first", SECOND: "second", THIRD: "third"}
EPICS = tuple(SLUG_OF)
ALPHA = "TST-01M585P7WKBH9YJ8E6NA73W4S9"
BRAVO = "TST-01M585P8MYP5WJAMJ89Z981GEG"
SX = "TST-01M585PFWZZXH4Y6KNMH1VK58H"
STORY_PATHS = {
    ALPHA: f"art/epics/{FIRST}/stories/{ALPHA}/story.md",
    BRAVO: f"art/epics/{FIRST}/stories/{BRAVO}/story.md",
    SX: f"art/epics/{SECOND}/stories/{SX}/story.md",
}
SLUGS = {ALPHA: "alpha", BRAVO: "bravo", SX: "sx"}
COVERS = {ALPHA: "SD-3", BRAVO: "SD-4", SX: "SD-3"}
BLOCKERS = {ALPHA: "bravo", BRAVO: "alpha", SX: "alpha"}
SEED_STATUSES = ("backlog", "researched", "covered", "resolved", "dropped", "deferred")
SEED_LAYERS = ("frontend", "backend", "infra")
_NUMBERED = re.compile(r"^(\d{4,})-(.+)$")


def slug_of(name: str) -> str:
    """The slug an old `NNNN-slug` name carries: the whole name when it carries no number."""
    found = _NUMBERED.match(name.strip())
    return found.group(2) if found else name.strip()


def directory_of(name: str) -> str:
    """The folder a name stands for among the epics the sandbox starts with: an id as typed, a slug or an old
    `NNNN-slug` name as the id of the epic with that slug, any other name as typed."""
    name = name.strip()
    if name in SLUG_OF:
        return name
    return next((e for e, slug in SLUG_OF.items() if slug == slug_of(name)), name)


class Epic:
    """An epic a user names, by its id, its slug or an old `NNNN-slug` name."""

    name: str | None

    @property
    def canonical(self) -> str:
        return directory_of(self.name or "")


@dataclass
class SeedAddArgs(Fixture):
    epic: str | None = None
    seed: str | None = None
    status: str | None = None
    layer: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[SeedAddArgs]:
        return (seed_add(), seed_add("0002-second", "SD-4", status="researched", layer="frontend"), seed_add("0009"),
                seed_add(status="weird"), seed_add(layer="cloud"))


@dataclass
class SeedRemoveArgs(Fixture):
    epic: str | None = None
    seed: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[SeedRemoveArgs]:
        return (seed_remove(), seed_remove("0002-second", "SD-4"), seed_remove("0009"))


@dataclass
class SetStatusArgs(Fixture):
    story: str | None = None
    status: str | None = None

    @property
    def trimmed(self) -> str:
        """The status as the tool keeps it: without the spaces and tabs around it."""
        return (self.status or "").strip()

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[SetStatusArgs]:
        return (set_status(), set_status(ALPHA, "Blocked: waiting"), set_status(ALPHA, "Not started"), set_status(ALPHA, "Done"),
                set_status(ALPHA, " Done "), set_status(ALPHA, "\tDone\t"), set_status(ALPHA, "In progress"), set_status(ALPHA, ""), set_status(ALPHA, "   "), set_status(ALPHA, "\t"),
                set_status("TST-NOPE"), set_status("TST-NOPE", ""))


@dataclass
class ConflictArgs(Fixture):
    story: str | None = None
    text: str | None = None
    clear: bool | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[ConflictArgs]:
        return (conflict(), conflict(ALPHA, "specs contradict"), conflict(ALPHA, None, clear=True), conflict(ALPHA, None),
                conflict(ALPHA, "criteria disagree", clear=True), conflict("TST-NOPE"))


@dataclass
class PathEpicArgs(Fixture):
    name: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[PathEpicArgs]:
        return (path_epic(), path_epic("first"), path_epic(FIRST), path_epic("nope"))


@dataclass
class CreateEpicArgs(Epic, Fixture):
    name: str | None = None
    title: str | None = None

    @property
    def slug(self) -> str:
        """The slug the new epic takes: the name, less the number of an old `NNNN-slug` name."""
        return slug_of(self.name or "")

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[CreateEpicArgs]:
        return (create_epic("second", "Second again"), create_epic("0001-first", "First again"))


@dataclass
class CreateStoryArgs(Fixture):
    epic: str | None = None
    slug: str | None = None
    title: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[CreateStoryArgs]:
        return (create_story("first", "alpha", "Alpha again"), create_story("0009-nope"))


@dataclass
class DeleteEpicArgs(Epic, Fixture):
    name: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[DeleteEpicArgs]:
        return (delete_epic("0009-nope"),)


@dataclass
class DeleteStoryArgs(Fixture):
    story: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[DeleteStoryArgs]:
        return (delete_story("TST-NOPE"),)


@dataclass
class UpdateStoryArgs(Fixture):
    story: str | None = None
    title: str | None = None
    covers: str | None = None
    depends: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[UpdateStoryArgs]:
        return (update_story(), update_story(ALPHA, "Story alpha", "(none)", "(none)"), update_story(BRAVO, "Renamed bravo", COVERS[BRAVO], BLOCKERS[BRAVO]),
                update_story("TST-NOPE"))


@dataclass
class UnblockArgs(Fixture):
    story: str | None = None
    epic: str | None = None
    all: bool | None = None
    status: str | None = None

    @property
    def target(self) -> str:
        """What the user named to unblock, as the tool repeats it."""
        return self.story or self.epic or ""

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[UnblockArgs]:
        return (unblock(), unblock(ALPHA, status="in-progress"), unblock(None, "first"), unblock(None, None, all=True),
                unblock(ALPHA, "first"), unblock(None, None), unblock("TST-NOPE"), unblock(None, "nope"),
                unblock(ALPHA, all=True))


@dataclass
class PathStoryArgs(Fixture):
    story: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[PathStoryArgs]:
        return (path_story(), path_story("TST-NOPE"))


@dataclass
class PathSpecArgs(Fixture):
    story: str | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[PathSpecArgs]:
        return (path_spec(), path_spec("TST-NOPE"))


@dataclass
class PathBranchArgs(Fixture):
    ref: str | None = None
    epic: bool | None = None

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[PathBranchArgs]:
        return (path_branch(), path_branch("0002-second", epic=True), path_branch("second", epic=True), path_branch(SECOND, epic=True),
                path_branch("TST-NOPE"))


def create_epic(name: str | None = "fourth", title: str | None = "Fourth epic") -> CreateEpicArgs:
    return CreateEpicArgs(name=name, title=title)


def create_story(epic: str | None = "third", slug: str | None = "delta", title: str | None = "Delta story") -> CreateStoryArgs:
    return CreateStoryArgs(epic=epic, slug=slug, title=title)


def delete_epic(name: str | None = "third") -> DeleteEpicArgs:
    return DeleteEpicArgs(name=name)


def delete_story(story: str | None = ALPHA) -> DeleteStoryArgs:
    return DeleteStoryArgs(story=story)


def update_story(story: str | None = ALPHA, title: str | None = "Renamed alpha", covers: str | None = "SD-3",
                 depends: str | None = "bravo") -> UpdateStoryArgs:
    return UpdateStoryArgs(story=story, title=title, covers=covers, depends=depends)


def unblock(story: str | None = None, epic: str | None = None, *, all: bool | None = None,
            status: str | None = None) -> UnblockArgs:
    return UnblockArgs(story=story, epic=epic, all=all, status=status)


def path_story(story: str | None = ALPHA) -> PathStoryArgs:
    return PathStoryArgs(story=story)


def path_spec(story: str | None = ALPHA) -> PathSpecArgs:
    return PathSpecArgs(story=story)


def path_branch(ref: str | None = ALPHA, *, epic: bool | None = None) -> PathBranchArgs:
    return PathBranchArgs(ref=ref, epic=epic)


@dataclass
class Nothing(Fixture):
    """A command that takes no argument the book varies: the words it needs are in its argv."""

    @classmethod
    def examples(cls, state: Any, by: Actor | None) -> Iterable[Nothing]:
        return (Nothing(),)


def nothing() -> Nothing:
    return Nothing()


def seed_add(epic: str | None = "0002-second", seed: str | None = "SD-3", *, status: str | None = None,
             layer: str | None = None) -> SeedAddArgs:
    return SeedAddArgs(epic=epic, seed=seed, status=status, layer=layer)


def seed_remove(epic: str | None = "0002-second", seed: str | None = "SD-3") -> SeedRemoveArgs:
    return SeedRemoveArgs(epic=epic, seed=seed)


def set_status(story: str | None = ALPHA, status: str | None = "in-progress") -> SetStatusArgs:
    return SetStatusArgs(story=story, status=status)


def conflict(story: str | None = ALPHA, text: str | None = "criteria disagree", *, clear: bool | None = None) -> ConflictArgs:
    return ConflictArgs(story=story, text=text, clear=clear)


def path_epic(name: str | None = "0001-first") -> PathEpicArgs:
    return PathEpicArgs(name=name)


__all__ = [
    "Nothing", "nothing",
    "BLOCKERS", "COVERS", "CreateEpicArgs", "CreateStoryArgs", "DeleteEpicArgs", "DeleteStoryArgs", "PathBranchArgs",
    "PathSpecArgs", "PathStoryArgs", "SLUGS", "UnblockArgs", "UpdateStoryArgs", "create_epic", "create_story",
    "delete_epic", "delete_story", "path_branch", "path_spec", "path_story", "unblock", "update_story",
    "ALPHA", "BRAVO", "FIRST", "SECOND", "SLUG_OF", "THIRD", "ConflictArgs", "EPICS", "PathEpicArgs", "SEED_LAYERS",
    "SEED_STATUSES", "STORY_PATHS", "SX", "SeedAddArgs", "SeedRemoveArgs", "SetStatusArgs", "conflict", "directory_of", "path_epic",
    "seed_add", "seed_remove", "set_status", "slug_of",
]
