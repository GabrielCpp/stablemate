"""The ostler commands the book plays: what a person types, and every way each one can end.
ostler prints its refusals on standard output and exits 1."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Files, Flag, Lines, Object, Positional, Str, Switch

from .model.actions import (AddEpic, AddSeed, ApplyLayout, BranchName, ClearBlocks, DropEpic, DropStory, EditStory, ListEpics, ListFiles,
                            MakeEpic, MakeStory, PathOfEpic, PruneEpic, RecordConflict, RemoveSeed, ReorderEpics, SetStoryStatus,
                            SpecPath, StoryPath)
from .model.files import MARKS

EPIC = Field(Str(classes={"an epic with no folder": "0009-nope"}), required=False,
             does="the epic to queue: its id, its slug, or an old NNNN-slug name read by its slug")
QUEUED = Field(Str(classes={"an epic the queue does not hold": "0009-nope"}), required=False,
               does="the epic to drop: its id, its slug, or an old NNNN-slug name read by its slug")
SEED_EPIC = Field(Str(classes={"an epic that does not exist": "0009"}), required=False, does="the epic that lists the seed")
SEED = Field(Str(), required=False, does="the seed's id, free text")
STORY = Field(Str(classes={"a story that does not exist": "TST-NOPE"}), required=False, does="the story's id")


class TodoAdd(Command):
    does = "Queue an epic, last or first, by its id, its slug or an old NNNN-slug name. The queue keeps the epic's id."
    program = "ostler"
    argv = ("--full-ids", "todo", "add", Positional("name"), Switch("--front", "front"))
    args = Object("AddArgs", name=EPIC, front=Field(Bool(), required=False, does="queue the epic first rather than last"))
    answers = (
        Exit(0, Lines(), "the epic is queued, with a warning when it has no epic.md yet"),
        Exit(1, Lines(), "the epic is already in the queue, matched by the name as typed or by the epic it stands for"),
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
    does = ("Move the named epics to the front of the queue in the order given; the rest keep their order after them. "
            "An epic named twice, by the same name or by two names that stand for it, is refused.")
    program = "ostler"
    argv = ("--full-ids", "todo", "reorder", Positional("first"), Positional("then"))
    args = Object(
        "ReorderArgs",
        first=Field(Str(classes={"an epic the queue does not hold": "0009-nope"}), required=False, does="the epic to put first"),
        then=Field(Str(classes={"an epic the queue does not hold": "0009-nope"}), required=False, does="the epic to put second"),
    )
    answers = (
        Exit(0, Lines(), "the queue is reordered"),
        Exit(1, Lines(), "the queue does not hold a named epic, and the message lists those it lacks, as typed; or two names "
                         "stand for the same queued epic, and the message names it as the queue spells it. "
                         "The queue file is left as it was. A missing epic is refused before a repeat"),
    )
    carries = ReorderEpics
    source = ("ostler/ostler/todo.py::reorder",)


class TodoList(Command):
    does = "Print the queue, one epic per line, first to last."
    program = "ostler"
    argv = ("--full-ids", "todo", "list")
    args = Object("ListArgs")
    answers = (
        Exit(0, Lines(), "the queued epics, or (none) when the queue is empty"),
        Exit(1, STDERR, "the shelf still names an epic folder by number and slug, as every command that reads the plan refuses"),
    )
    carries = ListEpics
    source = ("ostler/ostler/todo.py::list_epics", "ostler/ostler/layout.py::check", "ostler/ostler/layout.py::numbered_epics")


class LayoutApply(Command):
    does = ("Rename every epic and story folder on the shelf to its id, record the slug of each epic that names none, "
            "and point the queue entries at the id folders. A shelf already named by ids is left alone and said so.")
    program = "ostler"
    argv = ("--full-ids", "layout", "apply")
    args = Object("NoArgs")
    answers = (Exit(0, Lines(), "one line per slug recorded, folder renamed and queue repointed, or the line that nothing moved"),)
    carries = ApplyLayout
    source = ("ostler/ostler/cli.py::_cmd_layout", "ostler/ostler/layout.py::apply", "ostler/ostler/layout.py::_record_slug",
              "ostler/ostler/layout.py::_requeue")


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
    does = ("Set a story's status in its frontmatter and in its Implementation Status line. "
            "A status that is empty, or made only of spaces and tabs, is refused and no file changes.")
    program = "ostler"
    argv = ("--full-ids", "set-status", Positional("story"), Positional("status"))
    args = Object(
        "SetStatusArgs",
        story=STORY,
        status=Field(
            Str(classes={"an empty status": "", "a status of spaces": "   ", "a status of a tab": "\t",
                         "a status with spaces around it": " Done ",
                         "a status with tabs around it": "\tDone\t"}),
            required=False,
            does="the new status, free text. Any text is kept as typed apart from the spaces and tabs around it; "
                 "text with nothing but spaces and tabs in it is refused",
        ),
    )
    answers = (
        Exit(0, Lines(), "the status is set, written without the spaces and tabs around it"),
        Exit(1, Lines(), "no story has the id, or the status is empty or made only of spaces and tabs; the story file is left as it was"),
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
    does = "Print where an epic lives, relative to the repository: the folder named by its id."
    program = "ostler"
    argv = ("--full-ids", "path", "epic", Positional("name"))
    args = Object("PathEpicArgs", name=Field(Str(classes={"an epic with no folder": "nope"}), required=False, does="the epic, by id, slug or NNNN-slug"))
    answers = (Exit(0, Lines(), "the epic's id folder, or a folder named as typed when no epic has the name"),)
    carries = PathOfEpic
    source = ("ostler/ostler/path.py::epic_dir_under",)


class CreateEpic(Command):
    does = ("Create an epic: a folder named by the id it mints and an epic.md that records the slug, with no stories. "
            "An old NNNN-slug name gives the slug alone. A slug an epic already has is refused. The new epic is not queued.")
    program = "ostler"
    argv = ("--full-ids", "create", "epic", Positional("name"), Flag("--title", "title"))
    args = Object(
        "CreateEpicArgs",
        name=Field(Str(classes={"an epic that exists": "second"}), required=False, does="the epic's slug; an old NNNN-slug name gives its slug"),
        title=Field(Str(), required=False, does="the epic's title"),
    )
    answers = (
        Exit(0, Lines(opaque=("created epic",)), "the epic is created and its id minted; the line names the slug and the id"),
        Exit(1, Lines(), "an epic already has the slug, and the line names its folder"),
    )
    carries = MakeEpic
    source = ("ostler/ostler/crud.py::create_epic", "ostler/ostler/ids.py", "ostler/ostler/registry.py::epic_slug")


class CreateStory(Command):
    does = ("Add a story to an epic: a heading in epic.md and a story.md, in a folder named by the id it mints, with the "
            "sections a story carries. A slug the epic already holds is left alone and reported.")
    program = "ostler"
    argv = ("--full-ids", "create", "story", Positional("epic"), Positional("slug"), Flag("--title", "title"))
    args = Object(
        "CreateStoryArgs",
        epic=Field(Str(classes={"an epic with no folder": "0009-nope"}), required=False, does="the epic, by id, slug or NNNN-slug"),
        slug=Field(Str(), required=False, does="the story's slug"),
        title=Field(Str(), required=False, does="the story's title"),
    )
    answers = (
        Exit(0, Lines(opaque=("created story",)), "the story is created and its id minted, or the epic already holds the slug"),
        Exit(1, Lines(), "no epic has the name"),
    )
    carries = MakeStory
    source = ("ostler/ostler/crud.py::create_story", "ostler/ostler/crud.py::_story_block", "ostler/ostler/crud.py::_story_body",
              "ostler/ostler/registry.py::STORY_SECTIONS")


class DeleteEpic(Command):
    does = ("Delete an epic's folder, drop it from the queue and from the milestones that list it. "
            "An epic that is already gone is reported as absent, and the clean-up still runs.")
    program = "ostler"
    argv = ("--full-ids", "delete", "epic", Positional("name"))
    args = Object("DeleteEpicArgs", name=Field(Str(), required=False, does="the epic, by id, slug or NNNN-slug"))
    answers = (Exit(0, Lines(), "the epic is deleted and the line names its id folder, or it was already absent; the line says when the queue dropped it"),)
    carries = DropEpic
    source = ("ostler/ostler/crud.py::delete_epic",)


class DeleteCreatedEpic(Command):
    does = ("Delete an epic a command created in this world. The line names the folder, which carries the id the tool "
            "minted, so the book leaves the line out and reads the deletion from the commands that follow. The book types "
            "it without --full-ids, which changes nothing in a line that names a folder.")
    program = "ostler"
    argv = ("delete", "epic", Positional("name"))
    args = Object("DeleteEpicArgs", name=Field(Str(), required=False, does="the epic, by its slug or NNNN-slug"))
    answers = (Exit(0, Lines(opaque=("deleted epic '",)), "the epic is deleted, or was already absent"),)
    carries = DropEpic
    source = ("ostler/ostler/crud.py::delete_epic",)


class DeleteStory(Command):
    does = "Delete a story: its heading in epic.md and its folder."
    program = "ostler"
    argv = ("--full-ids", "delete", "story", Positional("story"))
    args = Object("DeleteStoryArgs", story=STORY)
    answers = (
        Exit(0, Lines(), "the story is deleted"),
        Exit(1, Lines(), "no story has the id"),
    )
    carries = DropStory
    source = ("ostler/ostler/crud.py::delete_story", "ostler/ostler/crud.py::_story_in_epic")


class UpdateStory(Command):
    does = ("Replace a story's title, covered seeds and blockers. The blockers are rewritten into the story's own "
            "Dependencies section, and (none) clears them.")
    program = "ostler"
    argv = ("--full-ids", "update", "story", Positional("story"), Flag("--title", "title"), Flag("--covers", "covers"),
            Flag("--depends", "depends"))
    args = Object(
        "UpdateStoryArgs",
        story=STORY,
        title=Field(Str(), required=False, does="the new title"),
        covers=Field(Str(), required=False, does="the seeds the story covers, or (none)"),
        depends=Field(Str(), required=False, does="the sibling slugs that block the story, or (none)"),
    )
    answers = (
        Exit(0, Lines(), "the epic's story block and the story's Dependencies are rewritten"),
        Exit(1, Lines(), "no story has the id"),
    )
    carries = EditStory
    source = ("ostler/ostler/crud.py::update_story", "ostler/ostler/crud.py::_write_dependencies",
              "ostler/ostler/crud.py::_dependency_lines")


class Unblock(Command):
    does = ("Clear the give-up stamp off a story, off an epic's stories or off every story, and restore a status. "
            "A story is blocked when its status starts with Blocked, Docs blocked or QA give-up.")
    program = "ostler"
    argv = ("--full-ids", "unblock", Positional("story"), Flag("--epic", "epic"), Switch("--all", "all"), Flag("--status", "status"))
    args = Object(
        "UnblockArgs",
        story=Field(Str(classes={"a story that does not exist": "TST-NOPE"}), required=False, does="one story's id"),
        epic=Field(Str(classes={"an epic that does not exist": "nope"}), required=False, does="every blocked story of this epic"),
        all=Field(Bool(), required=False, does="every blocked story of the repository"),
        status=Field(Str(), required=False, does="the status to restore; Not started when left out"),
    )
    answers = (
        Exit(0, Lines(), "the blocked stories take the status, or none was blocked"),
        Exit(1, Lines(), "no scope was named, two were, or the story or the epic does not exist"),
    )
    carries = ClearBlocks
    source = ("ostler/ostler/crud.py::unblock", "ostler/ostler/select.py::is_blocked", "ostler/ostler/select.py::epic_by_name",
              "ostler/ostler/cli.py::_dispatch")


class PathStory(Command):
    does = "Print the path of a story's story.md, relative to the repository."
    program = "ostler"
    argv = ("--full-ids", "path", "story", Positional("story"))
    args = Object("PathStoryArgs", story=STORY)
    answers = (
        Exit(0, Lines(), "the story's story.md path"),
        Exit(1, Lines(), "no story has the id"),
    )
    carries = StoryPath
    source = ("ostler/ostler/path.py::resolve_story",)


class PathSpec(Command):
    does = "Print the spec folder of a story, which is named by the story's id and need not exist yet."
    program = "ostler"
    argv = ("--full-ids", "path", "spec", Positional("story"))
    args = Object("PathSpecArgs", story=STORY)
    answers = (
        Exit(0, Lines(), "the story's spec folder under the specs root"),
        Exit(1, Lines(), "no story has the id"),
    )
    carries = SpecPath
    source = ("ostler/ostler/path.py::resolve_spec",)


class PathBranch(Command):
    does = "Print the git branch for a story, which is its slug, or for an epic with --epic, which is feat/ and its slug."
    program = "ostler"
    argv = ("--full-ids", "path", "branch", Positional("ref"), Switch("--epic", "epic"))
    args = Object(
        "PathBranchArgs",
        ref=Field(Str(classes={"a story that does not exist": "TST-NOPE"}), required=False, does="the story's id, or the epic's name with --epic"),
        epic=Field(Bool(), required=False, does="name the epic's branch instead of a story's"),
    )
    answers = (
        Exit(0, Lines(), "the branch name"),
        Exit(1, Lines(), "no story has the id"),
    )
    carries = BranchName
    source = ("ostler/ostler/path.py::resolve_branch",)


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("ostler/ostler/crud.py::set_status", "ostler/ostler/crud.py::add_seed")


ALL = (TodoAdd, TodoPrune, TodoReorder, TodoList, LayoutApply, SeedAdd, SeedRemove, SetStatus, Conflict, PathEpic, CreateEpic, CreateStory,
       DeleteEpic, DeleteCreatedEpic, DeleteStory, UpdateStory, Unblock, PathStory, PathSpec, PathBranch, Look)
