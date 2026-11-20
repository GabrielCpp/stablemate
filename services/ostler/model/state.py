"""The plan repository a person works in: the watched files it holds, and the epics and stories a command created
under an id the book cannot know."""

from __future__ import annotations

from datetime import date
from typing import cast

from ostler.book import Collection, State, Unique

from ..fixtures import ALPHA, SECOND, SLUG_OF, SLUGS, STORY_PATHS, slug_of
from .files import (BULLET_LINES, EPIC_PATHS, LEGACY, LEGACY_SLUG, NOT_STARTED, SEED_IDS, STATUS_LINES, STORY_FILES,
                    CONFLICT_LINES, FileRecord, holding, OLD_BULLET, OLD_LIST)
from .records import MintedEpic, MintedStory

SECOND_EPIC = f"art/epics/{SECOND}/epic.md"
KNOWN_SLUGS = {**SLUG_OF, LEGACY: LEGACY_SLUG}
MINTED = "<minted {}>"


class Plan(State):
    files = Collection(FileRecord, Unique("path"))
    minted = Collection(MintedEpic, Unique("slug"))
    stories = Collection(MintedStory, Unique("key"))

    def __init__(self, today: date):
        super().__init__(today)
        for path in STORY_FILES:
            self.files.items[path] = holding(path, NOT_STARTED, BULLET_LINES["Not started"])
        for path in EPIC_PATHS:
            epic = path.split("/")[2]
            listed = [sid for sid in STORY_PATHS if STORY_PATHS[sid].startswith(f"art/epics/{epic}/")]
            held = [m for sid in listed for m in (f"### {SLUGS[sid]}", f"- title: Story {SLUGS[sid]}")]
            self.files.items[path] = holding(path, f"slug: {SLUG_OF[epic]}", *held)
        self.files.items[OLD_LIST] = holding(OLD_LIST, OLD_BULLET)

    def rows(self) -> tuple[FileRecord, ...]:
        return tuple(sorted(self.files, key=lambda f: tuple(f.path.split("/"))))

    def row(self, entity: object) -> FileRecord:
        return cast(FileRecord, entity)

    def folders(self) -> dict[str, str]:
        """Each epic folder the shelf holds, with the slug of its epic: the folders the watch reads, then the epics
        a command created, under a stand-in for the id the tool minted."""
        found = {f.path.split("/")[2] for f in self.files if f.path.startswith("art/epics/") and f.path.endswith("/epic.md")}
        named = {folder: KNOWN_SLUGS.get(folder, slug_of(folder)) for folder in sorted(found)}
        return {**named, **{MINTED.format(e.slug): e.slug for e in sorted(self.minted, key=lambda e: e.slug)}}

    def epic_of(self, ref: str | None) -> str | None:
        """The folder of the epic a name stands for, by its id, then its folder, then its slug; an old `NNNN-slug`
        name stands for the epic with its slug. None when no epic has it."""
        ref = (ref or "").strip()
        if not ref:
            return None
        folders = self.folders()
        if ref in folders:
            return ref
        return next((folder for folder, slug in folders.items() if slug == slug_of(ref)), None)

    def resolve_epic(self, name: str | None) -> str:
        """The folder a command builds from an epic name: the epic's when one has it, else the name as typed."""
        return self.epic_of(name) or (name or "").strip()

    def stories_of(self, folder: str) -> tuple[str, ...]:
        """The slugs of the stories the epic in this folder holds."""
        seeded = (SLUGS[sid] for sid, path in STORY_PATHS.items() if path.split("/")[2] == folder and path in self.files.items)
        made = (s.slug for s in self.stories if s.epic == folder)
        return tuple(sorted((*seeded, *made)))

    def has_story(self, story: str) -> bool:
        return story in STORY_PATHS and STORY_PATHS[story] in self.files.items

    def numbered(self) -> tuple[str, ...]:
        """The epic folders the shelf still names by number and slug."""
        return tuple(f for f in self.folders() if slug_of(f) != f and not f.startswith("<"))


def story_stage(model: Plan) -> str:
    """Where the story alpha stands: its status, and whether a conflict is recorded on it."""
    held = model.files[STORY_PATHS[ALPHA]].holds
    status = next(name for name, line in STATUS_LINES.items() if line in held)
    return f"{status} with conflict" if any(line in held for line in CONFLICT_LINES) else status


def seed_stage(model: Plan) -> str:
    """Which seeds the second epic lists."""
    held = model.files[SECOND_EPIC].holds
    found = [i for i in SEED_IDS if any(b.startswith(f"### {i}\n") for b in held)]
    return " + ".join(found) or "no seeds"


def plan_stage(model: Plan) -> str:
    """Which stories each epic holds, epic by epic, each named by its slug."""
    return " ".join(f"{slug}({','.join(model.stories_of(folder))})" for folder, slug in model.folders().items())
