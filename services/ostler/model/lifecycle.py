"""The lifecycle matrices of a plan repository: how far a story and an epic's seeds
have come, and what each command does to them there."""

from __future__ import annotations

from datetime import date
from typing import Callable

from ostler.book import Axes, Scene

from ..commands import (Conflict, CreateEpic, CreateStory, DeleteCreatedEpic, DeleteEpic, DeleteStory, LayoutApply, Look, PathBranch, PathDesign, PathEpic, PathMilestone, PathNotes, PathSpec,
                        PathStory, SeedAdd, SeedRemove, SetStatus, Unblock, UpdateStory)
from ..fixtures import (ALPHA, BRAVO, FIRST, SECOND, SX, THIRD, conflict, create_epic, create_story, delete_epic, delete_story, path_branch, path_design, path_epic, path_milestone, path_notes,
                        path_spec, path_story, seed_add, seed_remove, set_status, unblock, update_story)
from ..graph import (EnvResetUnknown, EnvUpUnknown, RunGrpcPlan, RunPhonePlan, RunWebPlan, ValidatePhonePlan, ValidateWebPlan, VetDryRun, VetOfUnknownStory,
                     VetWithoutArguments, VetWithoutRegions, EnvAddress, EnvDown, EnvExec, EnvRender, EnvRenderUnknown, BacklogAdopt, BacklogAdd, CutFrames, LintBadPlan, LintPlan, ReadLedger, RecordAssertion, RecordStep, ReplayRun,
                     ReportRun, RunBadPlan, RunPlan, StartSession, StopSession, ValidateBadPlan, ValidatePlan, BacklogDropWithoutReason, BacklogList, BacklogPrune, BuildIndex, CleanQaScratch, CreateMilestone,
                     CreateSpec, CreateSpecOfUnknownStory, Doctor, EditRename, EditRenameUnknown, EnvCheck, EnvList, EnvListAll, EnvPrune, EnvSchema,
                     EvictCache, ListArtifactKinds, ListEpicRows, ListRepoStoryRows, ListStoryRows, ListUnknownRepoRows, MilestoneEpicsBoth,
                     MilestoneEpicsFirst, MilestoneEpicsUnknown, MilestoneSourceItem, NextEpic, NextStory, QueryCovering,
                     ScaffoldArtifact, SearchPlan, ShowChecks, TemplateApply, TemplateDelete, TemplateFind, TemplateNew,
                     VetArtifact)
from ..books import (CheckBook, DrawBook, ExplainBook, ExplainNothing, SearchUnmovedBook, MoveBook, ExploreBook, IndexBook, ListBookDecisions, ListBookPages, RunBook,
                     SearchBook)
from ..events import CopyInAnOldEpic
from ..fixtures import nothing
from .documents import holds
from .files import (RENDERED, LEDGER, QA_EVIDENCE, SESSION, ARTIFACT, CLOSED, FIRST_EPIC_LISTED, GUIDANCE, MILESTONE, OPEN, RECORD, SECOND_EPIC_LISTED,
                    SOURCE_ITEM, SPEC, TEMPLATE_DECLARED, TEMPLATES)
from .state import Plan, plan_stage, seed_stage, story_stage

TODAY = date(2026, 11, 12)

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
    "unblock the story": lambda m: Unblock(unblock(ALPHA)),
    "unblock the story to a status": lambda m: Unblock(unblock(ALPHA, status="in-progress")),
    "unblock the epic": lambda m: Unblock(unblock(None, "first")),
    "unblock the epic by its old name": lambda m: Unblock(unblock(None, "0001-first")),
    "unblock the epic by id": lambda m: Unblock(unblock(None, FIRST)),
    "unblock the second epic": lambda m: Unblock(unblock(None, "0002-second")),
    "unblock every story": lambda m: Unblock(unblock(None, None, all=True)),
    "unblock with nothing named": lambda m: Unblock(unblock()),
    "unblock a story and an epic": lambda m: Unblock(unblock(ALPHA, "first")),
    "unblock every story and a story": lambda m: Unblock(unblock(ALPHA, all=True)),
    "unblock an unknown story": lambda m: Unblock(unblock("TST-NOPE")),
    "unblock an unknown epic": lambda m: Unblock(unblock(None, "nope")),
    "update the story": lambda m: UpdateStory(update_story(ALPHA, "Renamed alpha", "SD-3", "bravo")),
    "update the story to clear its links": lambda m: UpdateStory(update_story(ALPHA, "Story alpha", "(none)", "(none)")),
    "update an unknown story": lambda m: UpdateStory(update_story("TST-NOPE")),
    "path of the story": lambda m: PathStory(path_story(ALPHA)),
    "path of an unknown story": lambda m: PathStory(path_story("TST-NOPE")),
    "spec path of the story": lambda m: PathSpec(path_spec(ALPHA)),
    "spec path of an unknown story": lambda m: PathSpec(path_spec("TST-NOPE")),
    "notes path": lambda m: PathNotes(path_notes()),
    "design path": lambda m: PathDesign(path_design()),
    "design path of a slug that is not kebab-case": lambda m: PathDesign(path_design("Bad Slug")),
    "branch of the story": lambda m: PathBranch(path_branch(ALPHA)),
    "branch of an unknown story": lambda m: PathBranch(path_branch("TST-NOPE")),
    "branch of an epic": lambda m: PathBranch(path_branch("second", epic=True)),
    "branch of an epic by id": lambda m: PathBranch(path_branch(SECOND, epic=True)),
    "reset a copy that is not up": lambda m: EnvResetUnknown(nothing()),
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


PLAN_SCENES = (
    Scene("seeded", "the plan holds its three epics", lambda today: ()),
    Scene("story created", "a story was added to the third epic", lambda today: (CreateStory(create_story("third", "delta")),)),
    Scene("epic created", "a fourth epic was created", lambda today: (CreateEpic(create_epic("fourth", "Fourth epic")),)),
    Scene("story deleted", "the story bravo was deleted", lambda today: (DeleteStory(delete_story(BRAVO)),)),
    Scene("epic deleted", "the third epic was deleted", lambda today: (DeleteEpic(delete_epic("third")),)),
)

PLAN_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "create an epic": lambda m: CreateEpic(create_epic("fifth", "Fifth epic")),
    "create an epic by an old NNNN-slug name": lambda m: CreateEpic(create_epic("0007-seventh", "Seventh epic")),
    "create an epic that exists": lambda m: CreateEpic(create_epic("second", "Second again")),
    "create an epic by the old name of one that exists": lambda m: CreateEpic(create_epic("0001-first", "First again")),
    "create a story": lambda m: CreateStory(create_story("third", "delta")),
    "create a story by the epic's old name": lambda m: CreateStory(create_story("0002-second", "delta")),
    "create a story by the epic's id": lambda m: CreateStory(create_story(THIRD, "delta")),
    "create a story in the created epic": lambda m: CreateStory(create_story("fourth", "delta")),
    "create a story that exists": lambda m: CreateStory(create_story("first", "alpha", "Alpha again")),
    "create a story in an unknown epic": lambda m: CreateStory(create_story("0009-nope")),
    "delete an epic": lambda m: DeleteEpic(delete_epic("third")),
    "delete an epic by its old name": lambda m: DeleteEpic(delete_epic("0002-second")),
    "delete an epic with stories": lambda m: DeleteEpic(delete_epic("first")),
    "delete an epic that is gone": lambda m: DeleteEpic(delete_epic("0009-nope")),
    "delete an epic by id": lambda m: DeleteEpic(delete_epic(THIRD)),
    "delete the created epic": lambda m: DeleteCreatedEpic(delete_epic("fourth")),
    "delete the created epic by an old name": lambda m: DeleteCreatedEpic(delete_epic("0004-fourth")),
    "delete a story": lambda m: DeleteStory(delete_story(ALPHA)),
    "delete the story of the second epic": lambda m: DeleteStory(delete_story(SX)),
    "delete an unknown story": lambda m: DeleteStory(delete_story("TST-NOPE")),
    "update a story": lambda m: UpdateStory(update_story(BRAVO, "Renamed bravo", "SD-4", "alpha")),
    "update an unknown story": lambda m: UpdateStory(update_story("TST-NOPE")),
    "look": lambda m: Look(),
}


def milestone_stage(model: Plan) -> str:
    """How far the milestone ms has come: not made, made, and the epics and items it lists."""
    held = holds(model, MILESTONE)
    if MILESTONE not in model.files.items:
        return "none"
    epics = sum(1 for line in (FIRST_EPIC_LISTED, SECOND_EPIC_LISTED) if line in held)
    return f"{epics} epics" + (" + item" if SOURCE_ITEM in held else "")


def record_stage(model: Plan) -> str:
    """The Register's record Fix thing: not filed, open or done."""
    if any(f.path.startswith("art/backlogs/acme/general/") for f in model.files):
        return "adopted"
    if RECORD not in model.files.items:
        return "none"
    return "done" if CLOSED in holds(model, RECORD) else "open" if OPEN in holds(model, RECORD) else "filed"


def spec_stage(model: Plan) -> str:
    """Which of the story alpha's spec documents exist."""
    found = [name for name, path in (("spec", SPEC), ("artifact", ARTIFACT)) if path in model.files.items]
    return " + ".join(found) or "none"


def template_stage(model: Plan) -> str:
    """Whether the template tpl is declared, and whether its guidance is written."""
    declared = TEMPLATE_DECLARED in holds(model, TEMPLATES)
    return ("declared" if declared else "none") + (" + guidance" if GUIDANCE in model.files.items else "")


def reads_stage(model: Plan) -> str:
    return "plan"


def qa_stage(model: Plan) -> str:
    """What the spec folder of the QA plan holds: a ledger, evidence of a batch run, an open session."""
    parts = [name for name, path in (("ledger", LEDGER), ("evidence", QA_EVIDENCE), ("open", SESSION)) if path in model.files.items]
    return " + ".join(parts) or "none"


READ_SCENES = (Scene("plan", "the plan as the sandbox starts", lambda today: ()),)

READ_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "doctor": lambda m: Doctor(nothing()),
    "list the epics": lambda m: ListEpicRows(nothing()),
    "list the stories": lambda m: ListStoryRows(nothing()),
    "list one repo's stories": lambda m: ListRepoStoryRows(nothing()),
    "list the stories of an unknown repo": lambda m: ListUnknownRepoRows(nothing()),
    "search": lambda m: SearchPlan(nothing()),
    "build the index": lambda m: BuildIndex(nothing()),
    "query the stories covering a seed": lambda m: QueryCovering(nothing()),
    "next epic": lambda m: NextEpic(nothing()),
    "next story": lambda m: NextStory(nothing()),
    "show the checks": lambda m: ShowChecks(nothing()),
    "evict the cache": lambda m: EvictCache(nothing()),
    "rename a slug, dry run": lambda m: EditRename(nothing()),
    "rename a slug no document holds": lambda m: EditRenameUnknown(nothing()),
    "list the artifact kinds": lambda m: ListArtifactKinds(nothing()),
    "clean QA scratch": lambda m: CleanQaScratch(nothing()),
    "env schema": lambda m: EnvSchema(nothing()),
    "env check": lambda m: EnvCheck(nothing()),
    "env list": lambda m: EnvList(nothing()),
    "env list all": lambda m: EnvListAll(nothing()),
    "env prune, dry run": lambda m: EnvPrune(nothing()),
    "look": lambda m: Look(),
}

QA_SCENES = (
    Scene("none", "no plan has run", lambda today: ()),
    Scene("ledger + evidence", "the plan ran in batch mode", lambda today: (RunPlan(nothing()),)),
    Scene("ledger + open", "a session is open", lambda today: (StartSession(nothing()),)),
    Scene("ledger", "a session was opened and closed", lambda today: (StartSession(nothing()), StopSession(nothing()))),
)

QA_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "lint the plan": lambda m: LintPlan(nothing()),
    "lint a plan that breaks the lint": lambda m: LintBadPlan(nothing()),
    "validate the plan": lambda m: ValidatePlan(nothing()),
    "validate a plan that breaks the lint": lambda m: ValidateBadPlan(nothing()),
    "run the plan": lambda m: RunPlan(nothing()),
    "run a plan that breaks the lint": lambda m: RunBadPlan(nothing()),
    "report": lambda m: ReportRun(nothing()),
    "replay": lambda m: ReplayRun(nothing()),
    "read the ledger": lambda m: ReadLedger(nothing()),
    "cut frames": lambda m: CutFrames(nothing()),
    "start a session": lambda m: StartSession(nothing()),
    "record a step": lambda m: RecordStep(nothing()),
    "record an assertion": lambda m: RecordAssertion(nothing()),
    "stop the session": lambda m: StopSession(nothing()),
    "look": lambda m: Look(),
}


BOOK_SCENES = (Scene("demo", "the sandbox holds the book demo", lambda today: ()),)

BOOK_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "check": lambda m: CheckBook(nothing()),
    "index": lambda m: IndexBook(nothing()),
    "search": lambda m: SearchBook(nothing()),
    "explain": lambda m: ExplainBook(nothing()),
    "explain a name the book lacks": lambda m: ExplainNothing(nothing()),
    "search a book left in the repository": lambda m: SearchUnmovedBook(nothing()),
    "move a flat book": lambda m: MoveBook(nothing()),
    "list the decisions": lambda m: ListBookDecisions(nothing()),
    "list the book pages": lambda m: ListBookPages(nothing()),
    "explore": lambda m: ExploreBook(nothing()),
    "run": lambda m: RunBook(nothing()),
    "draw": lambda m: DrawBook(nothing()),
    "look": lambda m: Look(),
}


def book_stage(model: Plan) -> str:
    return "demo"


def stack_stage(model: Plan) -> str:
    return "rendered" if RENDERED in model.files.items else "down"


STACK_SCENES = (
    Scene("down", "the shared copy is not rendered", lambda today: ()),
    Scene("rendered", "the shared copy is rendered", lambda today: (EnvRender(nothing()),)),
)

STACK_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "render": lambda m: EnvRender(nothing()),
    "render a book that has no stack": lambda m: EnvRenderUnknown(nothing()),
    "tear down": lambda m: EnvDown(nothing()),
    "address": lambda m: EnvAddress(nothing()),
    "exec": lambda m: EnvExec(nothing()),
    "look": lambda m: Look(),
}


def targets_stage(model: Plan) -> str:
    return "plan"


TARGET_SCENES = (Scene("plan", "the sandbox holds plans for a browser, a phone and a gRPC service, and no browser, device or server", lambda today: ()),)

TARGET_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "validate the browser plan": lambda m: ValidateWebPlan(nothing()),
    "validate the phone plan": lambda m: ValidatePhonePlan(nothing()),
    "run the browser plan": lambda m: RunWebPlan(nothing()),
    "run the phone plan": lambda m: RunPhonePlan(nothing()),
    "run the gRPC plan": lambda m: RunGrpcPlan(nothing()),
    "vet with no arguments": lambda m: VetWithoutArguments(nothing()),
    "vet with no regions file": lambda m: VetWithoutRegions(nothing()),
    "vet an unknown story": lambda m: VetOfUnknownStory(nothing()),
    "vet, dry run": lambda m: VetDryRun(nothing()),
    "bring up a book with no stack": lambda m: EnvUpUnknown(nothing()),
    "look": lambda m: Look(),
}


MILESTONE_SCENES = (
    Scene("none", "no milestone exists", lambda today: ()),
    Scene("0 epics", "the milestone ms was created", lambda today: (CreateMilestone(nothing()),)),
    Scene("1 epics", "the milestone lists the first epic", lambda today: (CreateMilestone(nothing()), MilestoneEpicsFirst(nothing()))),
    Scene("2 epics + item", "the milestone lists two epics and owns an item",
          lambda today: (CreateMilestone(nothing()), MilestoneEpicsBoth(nothing()), MilestoneSourceItem(nothing()))),
)

MILESTONE_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "create": lambda m: CreateMilestone(nothing()),
    "list the first epic": lambda m: MilestoneEpicsFirst(nothing()),
    "list two epics": lambda m: MilestoneEpicsBoth(nothing()),
    "list an epic that does not exist": lambda m: MilestoneEpicsUnknown(nothing()),
    "own an item": lambda m: MilestoneSourceItem(nothing()),
    "path of the milestone": lambda m: PathMilestone(path_milestone()),
    "path of an unknown milestone": lambda m: PathMilestone(path_milestone("nope")),
    "look": lambda m: Look(),
}

RECORD_SCENES = (
    Scene("none", "the Register holds no record", lambda today: ()),
    Scene("open", "the record is filed", lambda today: (BacklogAdd(nothing()),)),
    Scene("done", "the record is closed", lambda today: (BacklogAdd(nothing()), BacklogPrune(nothing()))),
    Scene("adopted", "an old list was imported as records", lambda today: (BacklogAdopt(nothing()),)),
)

RECORD_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "file": lambda m: BacklogAdd(nothing()),
    "list": lambda m: BacklogList(nothing()),
    "close": lambda m: BacklogPrune(nothing()),
    "drop with no reason": lambda m: BacklogDropWithoutReason(nothing()),
    "adopt the old list": lambda m: BacklogAdopt(nothing()),
    "look": lambda m: Look(),
}

SPEC_SCENES = (
    Scene("none", "the story has no spec document", lambda today: ()),
    Scene("spec", "the story has its plan spec", lambda today: (CreateSpec(nothing()),)),
    Scene("artifact", "the story has a scaffolded artifact", lambda today: (ScaffoldArtifact(nothing()),)),
)

SPEC_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "create the spec": lambda m: CreateSpec(nothing()),
    "create the spec of an unknown story": lambda m: CreateSpecOfUnknownStory(nothing()),
    "scaffold the artifact": lambda m: ScaffoldArtifact(nothing()),
    "vet the artifact": lambda m: VetArtifact(nothing()),
    "look": lambda m: Look(),
}

TEMPLATE_SCENES = (
    Scene("none", "no template is declared", lambda today: ()),
    Scene("declared", "the template tpl is declared", lambda today: (TemplateNew(nothing()),)),
    Scene("declared + guidance", "the template tpl is declared and applied",
          lambda today: (TemplateNew(nothing()), TemplateApply(nothing()))),
)

TEMPLATE_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "declare": lambda m: TemplateNew(nothing()),
    "find": lambda m: TemplateFind(nothing()),
    "apply": lambda m: TemplateApply(nothing()),
    "path of an epic by its old name": lambda m: PathEpic(path_epic("0001-first")),
    "path of an epic by id": lambda m: PathEpic(path_epic(FIRST)),
    "path of an epic by slug": lambda m: PathEpic(path_epic("first")),
    "path of an epic with no folder": lambda m: PathEpic(path_epic("nope")),
    "delete": lambda m: TemplateDelete(nothing()),
    "look": lambda m: Look(),
}


def layout_stage(model: Plan) -> str:
    """Whether the shelf still names an epic folder by number and slug."""
    return "numbered" if model.numbered() else "ids"


LAYOUT_SCENES = (
    Scene("ids", "every epic folder is named by its id", lambda today: ()),
    Scene("numbered", "a person copied in an epic folder from the old layout", lambda today: (CopyInAnOldEpic(),)),
)

LAYOUT_ACTIONS: dict[str, Callable[[Plan], object]] = {
    "path of an epic": lambda m: PathEpic(path_epic("first")),
    "apply the layout": lambda m: LayoutApply(nothing()),
    "look": lambda m: Look(),
}


MATRICES = (
    Axes[Plan]("story", TODAY, STORY_SCENES, STORY_ACTIONS, story_stage, state_of=lambda m, _: story_stage(m)),
    Axes[Plan]("reads", TODAY, READ_SCENES, READ_ACTIONS, reads_stage, state_of=lambda m, _: reads_stage(m)),
    Axes[Plan]("targets", TODAY, TARGET_SCENES, TARGET_ACTIONS, targets_stage, state_of=lambda m, _: targets_stage(m)),
    Axes[Plan]("stack", TODAY, STACK_SCENES, STACK_ACTIONS, stack_stage, state_of=lambda m, _: stack_stage(m)),
    Axes[Plan]("book", TODAY, BOOK_SCENES, BOOK_ACTIONS, book_stage, state_of=lambda m, _: book_stage(m)),
    Axes[Plan]("qa", TODAY, QA_SCENES, QA_ACTIONS, qa_stage, state_of=lambda m, _: qa_stage(m)),
    Axes[Plan]("milestone", TODAY, MILESTONE_SCENES, MILESTONE_ACTIONS, milestone_stage, state_of=lambda m, _: milestone_stage(m)),
    Axes[Plan]("record", TODAY, RECORD_SCENES, RECORD_ACTIONS, record_stage, state_of=lambda m, _: record_stage(m)),
    Axes[Plan]("spec", TODAY, SPEC_SCENES, SPEC_ACTIONS, spec_stage, state_of=lambda m, _: spec_stage(m)),
    Axes[Plan]("template", TODAY, TEMPLATE_SCENES, TEMPLATE_ACTIONS, template_stage, state_of=lambda m, _: template_stage(m)),
    Axes[Plan]("plan", TODAY, PLAN_SCENES, PLAN_ACTIONS, plan_stage, state_of=lambda m, _: plan_stage(m)),
    Axes[Plan]("seeds", TODAY, SEED_SCENES, SEED_ACTIONS, seed_stage, state_of=lambda m, _: seed_stage(m)),
    Axes[Plan]("layout", TODAY, LAYOUT_SCENES, LAYOUT_ACTIONS, layout_stage, state_of=lambda m, _: layout_stage(m)),
)
