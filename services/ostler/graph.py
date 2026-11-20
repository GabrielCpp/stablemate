"""The ostler commands whose words the book fixes in the argv: reads of the plan, and the commands that write a
milestone, a record, a decision, a spec, an artifact or a template. Each is declared once per call it plays."""

from __future__ import annotations

from ostler.book import STDERR, Command, Exit, Lines, Object

from .model import documents as act

ARGS = Object("NoArgs")
OPAQUE = Lines(opaque=("",))
OSTLER = ("ostler/ostler/cli.py::_dispatch", "ostler/ostler/model.py", "ostler/ostler/layout.py", "ostler/ostler/index.py")


class Doctor(Command):
    does = "Check the planning graph's conformance and referential integrity, and print each finding."
    program = "ostler"
    argv = ("--full-ids", "doctor")
    args = ARGS
    answers = (
        Exit(1, OPAQUE, "the graph has an error-level finding; the sandbox's stories and epics are bare scaffolds, so every run reports them"),
    )
    carries = act.Examining
    source = ("ostler/ostler/doctor.py", "ostler/ostler/finding.py", "ostler/ostler/schemas.py", "ostler/ostler/schema/epic.schema.json",
              "ostler/ostler/schema/story.schema.json", "ostler/ostler/schema/milestone.schema.json", "ostler/ostler/adr.py",
              "ostler/ostler/pages.py", "ostler/ostler/dynamic_registry.py", "ostler/ostler/manifest.py", *OSTLER)


class ListEpicRows(Command):
    does = "Print one JSON line for each epic."
    program = "ostler"
    argv = ("--full-ids", "list", "--type", "epic")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the epics, or (none)"),)
    carries = act.Reading
    source = ("ostler/ostler/query.py::list_entities",)


class ListStoryRows(Command):
    does = "Print one JSON line for each story."
    program = "ostler"
    argv = ("--full-ids", "list", "--type", "story")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the stories, or (none)"),)
    carries = act.Reading
    source = ("ostler/ostler/query.py::list_entities",)


class SearchPlan(Command):
    does = "Rank the sections of the current book and decisions against a query."
    program = "ostler"
    argv = ("--full-ids", "search", "alpha")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the ranked hits, or (none)"),)
    carries = act.Reading
    source = ("ostler/ostler/query.py::search", "ostler/ostler/textindex.py")


class BuildIndex(Command):
    does = "Build or refresh the full-text index and report its counts."
    program = "ostler"
    argv = ("--full-ids", "index", "build")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the index is built, and the line counts its sections and files"),)
    carries = act.Reading
    source = ("ostler/ostler/cli.py::_cmd_index", "ostler/ostler/textindex.py::build")


class QueryCovering(Command):
    does = "List the stories that cover a seed."
    program = "ostler"
    argv = ("--full-ids", "query", "stories-covering-seed", "SD-3")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the stories, or (none)"),)
    carries = act.Reading
    source = ("ostler/ostler/query.py::query",)


class NextEpic(Command):
    does = "Print the first epic, in milestone order, that has unfinished work."
    program = "ostler"
    argv = ("--full-ids", "next-epic")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the epic as JSON, or (none)"),)
    carries = act.Reading
    source = ("ostler/ostler/select.py::next_epic",)


class NextStory(Command):
    does = "Print the next runnable story of an epic."
    program = "ostler"
    argv = ("--full-ids", "next-story", "first")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the story as JSON, or (none)"),)
    carries = act.Reading
    source = ("ostler/ostler/select.py::next_story",)


class ShowChecks(Command):
    does = "Print the named checks a QA plan's verify takes and their signatures."
    program = "ostler"
    argv = ("--full-ids", "checks")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the vocabulary of checks"),)
    carries = act.Reading
    source = ("ostler/ostler/checks.py", "ostler/ostler/keys.py", "ostler/ostler/refs.py")


class EvictCache(Command):
    does = "Delete the parse index entries that aged out."
    program = "ostler"
    argv = ("--full-ids", "cache", "clean")
    args = ARGS
    answers = (Exit(0, Lines(), "the line counts the entries removed and names the index folder"),)
    carries = act.EvictCache
    source = ("ostler/ostler/cli.py::_cmd_cache", "ostler/ostler/index.py::clean")


class EditRename(Command):
    does = "Show, without writing, the edits that rename a story slug in every document."
    program = "ostler"
    argv = ("--full-ids", "edit", "rename", "alpha", "omega")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the diff, and a note that nothing was applied because --write was left out"),)
    carries = act.Reading
    source = ("ostler/ostler/edit.py", "ostler/ostler/answers.py")


class EditRenameUnknown(Command):
    does = "Refuse to rename a slug no document holds."
    program = "ostler"
    argv = ("--full-ids", "edit", "rename", "nothing", "here")
    args = ARGS
    answers = (
        Exit(1, Lines(), "no document holds the slug"),
    )
    carries = act.RenameUnknownSlug
    source = ("ostler/ostler/edit.py::rename",)


class CreateMilestone(Command):
    does = "Create the milestone ms with its numbered folder, in the proposed status."
    program = "ostler"
    argv = ("--full-ids", "create", "milestone", "ms", "--title", "Milestone")
    args = ARGS
    answers = (
        Exit(0, Lines(opaque=("created milestone",)), "the milestone is created and its id minted"),
        Exit(1, Lines(), "a milestone with that folder or slug exists"),
    )
    carries = act.MakeMilestone
    source = ("ostler/ostler/crud.py::create_milestone", "ostler/ostler/milestones.py")


class MilestoneEpicsFirst(Command):
    does = "Make the first epic the only epic of the milestone, and write it into the milestone's Epics section."
    program = "ostler"
    argv = ("--full-ids", "milestone", "epics", "ms", "first")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the milestone lists one epic"),
        Exit(1, Lines(), "no milestone has the name"),
    )
    carries = act.ListFirstEpic
    source = ("ostler/ostler/crud.py::set_milestone_epics", "ostler/ostler/crud.py::_write_milestone_epics")


class MilestoneEpicsBoth(Command):
    does = "List the first and then the second epic in the milestone, in that coding order."
    program = "ostler"
    argv = ("--full-ids", "milestone", "epics", "ms", "first", "second")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the milestone lists two epics"),
        Exit(1, Lines(), "no milestone has the name"),
    )
    carries = act.ListBothEpics
    source = ("ostler/ostler/crud.py::set_milestone_epics",)


class MilestoneEpicsUnknown(Command):
    does = "Refuse a milestone epic list that names an epic the plan lacks, and keep the list the milestone has."
    program = "ostler"
    argv = ("--full-ids", "milestone", "epics", "ms", "nope")
    args = ARGS
    answers = (
        Exit(1, Lines(), "no milestone has the name, or an epic named does not exist, and the message lists each"),
    )
    carries = act.ListUnknownEpic
    source = ("ostler/ostler/crud.py::set_milestone_epics",)


class MilestoneSourceItem(Command):
    does = "Set the backlog item ids a milestone owns."
    program = "ostler"
    argv = ("--full-ids", "milestone", "set-source-items", "ms", "SD-3")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the milestone owns one item"),
        Exit(1, Lines(), "no milestone has the name"),
    )
    carries = act.OwnSourceItem
    source = ("ostler/ostler/crud.py::set_milestone_source_items",)


class CreateSpec(Command):
    does = "Create the plan.md spec of the story alpha, typed spec.plan, or report that it is already typed."
    program = "ostler"
    argv = ("--full-ids", "create", "spec", "TST-01M585P7WKBH9YJ8E6NA73W4S9", "plan.md", "--title", "T")
    args = ARGS
    answers = (Exit(0, Lines(), "the spec is created, or it already carries its type"),)
    carries = act.TypeSpec
    source = ("ostler/ostler/crud.py::create_spec", "ostler/ostler/registry.py::spec_type_for")


class CreateSpecOfUnknownStory(Command):
    does = "Refuse a spec for a story id no story has."
    program = "ostler"
    argv = ("--full-ids", "create", "spec", "TST-NOPE", "plan.md")
    args = ARGS
    answers = (
        Exit(1, Lines(), "no story has the id"),
    )
    carries = act.TypeSpecOfUnknownStory
    source = ("ostler/ostler/path.py::resolve_spec",)


class BacklogAdd(Command):
    does = "File the record Fix thing on the Register, under the repository acme and the area web, with an id of the caller's."
    program = "ostler"
    argv = ("--full-ids", "backlog", "add", "Fix thing", "--repo", "acme", "--area", "web", "--id", "TST-01M7N888KSZ21DR28M6BSGQTY2")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the record is filed, open"),
        Exit(1, Lines(), "a record already has the id"),
    )
    carries = act.FileRecordOfWork
    source = ("ostler/ostler/register.py", "ostler/ostler/cli.py::_file_person")


class BacklogList(Command):
    does = "List the Register's records, one line each: id, repository, area, status, pattern and summary."
    program = "ostler"
    argv = ("--full-ids", "backlog", "list")
    args = ARGS
    answers = (Exit(0, Lines(), "the records, or (none)"),)
    carries = act.ListRecords
    source = ("ostler/ostler/register.py::records", "ostler/ostler/register.py::listing")


class BacklogPrune(Command):
    does = "Close the record as done."
    program = "ostler"
    argv = ("--full-ids", "backlog", "prune", "TST-01M7N888KSZ21DR28M6BSGQTY2")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the record is closed, or was already done"),
        Exit(1, Lines(), "no record has the id"),
    )
    carries = act.CloseRecord
    source = ("ostler/ostler/register.py::close", "ostler/ostler/cli.py::_prune_record")


class BacklogDropWithoutReason(Command):
    does = "Refuse to close a record as dropped without a reason."
    program = "ostler"
    argv = ("--full-ids", "backlog", "prune", "TST-01M7N888KSZ21DR28M6BSGQTY2", "--as", "dropped")
    args = ARGS
    answers = (Exit(1, Lines(), "dropped and promoted need a reason"),)
    carries = act.DropRecordWithoutReason
    source = ("ostler/ostler/cli.py::_prune_record",)


class FileDecision(Command):
    does = "File an empty decision use-x for the repository acme, with a one-line summary."
    program = "ostler"
    argv = ("--full-ids", "decisions", "add", "use-x", "--repo", "acme", "--summary", "Use x")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the decision file's path"),
        Exit(1, Lines(), "a decision with the slug exists"),
    )
    carries = act.FileDecision
    source = ("ostler/ostler/decisions.py",)


class TemplateNew(Command):
    does = "Declare the template tpl with one kind, docs."
    program = "ostler"
    argv = ("--full-ids", "template", "new", "tpl", "docs")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the template is declared in .agents/templates.yml"),
        Exit(1, Lines(), "a template has the name"),
    )
    carries = act.DeclareTemplate
    source = ("ostler/ostler/templates.py::new", "ostler/ostler/dynamic_registry.py")


class TemplateFind(Command):
    does = "Print the definition of the template tpl, or (none)."
    program = "ostler"
    argv = ("--full-ids", "template", "find", "tpl")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the template as JSON, or (none)"),)
    carries = act.ShowTemplate
    source = ("ostler/ostler/templates.py::find",)


class TemplateApply(Command):
    does = "Scaffold the template's folders and write its guidance into CLAUDE.md."
    program = "ostler"
    argv = ("--full-ids", "template", "apply", "tpl")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the guidance is written"),
        Exit(1, Lines(), "no template has the name"),
    )
    carries = act.ApplyTemplate
    source = ("ostler/ostler/templates.py::apply",)


class TemplateDelete(Command):
    does = "Delete the template tpl."
    program = "ostler"
    argv = ("--full-ids", "template", "delete", "tpl")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the template is deleted"),
        Exit(1, Lines(), "no template has the name"),
    )
    carries = act.DeleteTemplate
    source = ("ostler/ostler/templates.py::delete", "ostler/ostler/crud_generic.py")


class ListArtifactKinds(Command):
    does = "List the kinds of workflow artifact ostler can scaffold and vet."
    program = "ostler"
    argv = ("--full-ids", "artifact", "list")
    args = ARGS
    answers = (Exit(0, OPAQUE, "one JSON line for each kind"),)
    carries = act.Reading
    source = ("ostler/ostler/artifact/__init__.py", "ostler/ostler/artifact/kinds.py", "ostler/ostler/untyped.py")


class ScaffoldArtifact(Command):
    does = "Write the skeleton of a plan-context artifact into the spec folder of the story alpha."
    program = "ostler"
    argv = ("--full-ids", "artifact", "scaffold", "plan-context", "--spec", "TST-01M585P7WKBH9YJ8E6NA73W4S9")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the skeleton is written"),
        Exit(1, Lines(), "the artifact exists, and --force would overwrite it"),
    )
    carries = act.ScaffoldArtifact
    source = ("ostler/ostler/artifact/kinds.py::scaffold", "ostler/ostler/artifact/run.py")


class VetArtifact(Command):
    does = "Check the plan-context artifact of the story alpha against its contract."
    program = "ostler"
    argv = ("--full-ids", "artifact", "vet", "plan-context", "--spec", "TST-01M585P7WKBH9YJ8E6NA73W4S9")
    args = ARGS
    answers = (
        Exit(1, Lines(), "the artifact does not exist, or the problems it has are listed"),
    )
    carries = act.VetArtifact
    source = ("ostler/ostler/artifact/kinds.py::vet",)


class CleanQaScratch(Command):
    does = "List the legacy QA scratch directories under a folder and delete none without --yes."
    program = "ostler"
    argv = ("--full-ids", "qa", "clean", "--spec", "art/specs")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the folders found, none in the sandbox"),)
    carries = act.Reading
    source = ("ostler/ostler/qa/clean.py",)


class EnvSchema(Command):
    does = "Print the JSON Schema of a stack.yml."
    program = "ostler"
    argv = ("--full-ids", "env", "schema")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the schema"),)
    carries = act.Reading
    source = ("ostler/ostler/environments/cli.py", "ostler/ostler/environments/spec.py")


class EnvCheck(Command):
    does = "Check that every book's ops/stack.yml fits with the others."
    program = "ostler"
    argv = ("--full-ids", "env", "check")
    args = ARGS
    answers = (Exit(0, Lines(), "the count of services and books that fit together"),)
    carries = act.CountEnvServices
    source = ("ostler/ostler/environments/commands.py::cmd_check", "ostler/ostler/environments/__init__.py",
              "ostler/ostler/environments/secrets.py")


class EnvList(Command):
    does = "List the stack's services and the copies running them."
    program = "ostler"
    argv = ("--full-ids", "env", "ls")
    args = ARGS
    answers = (Exit(0, Lines(), "each book, then its services with what each is and the address it publishes"),)
    carries = act.ListEnvServices
    source = ("ostler/ostler/environments/commands.py::cmd_ls",)


class EnvListAll(Command):
    does = "List every copy on this machine, of any repo, marking the orphaned and idle ones."
    program = "ostler"
    argv = ("--full-ids", "env", "ls", "--all")
    args = ARGS
    answers = (Exit(0, Lines(), "one line for each copy with its worktree, state, age, last use and mark, or that none exists"),)
    carries = act.ListEveryCopy
    source = ("ostler/ostler/environments/commands.py::cmd_ls_all", "ostler/ostler/environments/runtime.py")


class EnvPrune(Command):
    does = "Say which copies prune would tear down or stop, and act on none."
    program = "ostler"
    argv = ("--full-ids", "env", "prune", "--dry-run")
    args = ARGS
    answers = (Exit(0, Lines(), "one line for each orphaned or idle copy, or that there is nothing to prune"),)
    carries = act.PruneNothing
    source = ("ostler/ostler/environments/commands.py::cmd_prune", "ostler/ostler/environments/runtime.py")


class BacklogAdopt(Command):
    does = "Import an old bullet list as records on the Register, once, and delete the list."
    program = "ostler"
    argv = ("--full-ids", "backlog", "adopt", "old-backlog.md", "--repo", "acme")
    args = ARGS
    answers = (
        Exit(0, Lines(), "one listing line for each record, then how many were imported"),
        Exit(1, Lines(), "the list is not there"),
    )
    carries = act.AdoptList
    source = ("ostler/ostler/register_import.py", "ostler/ostler/cli.py::_adopt_list", "ostler/ostler/result.py")


class LintPlan(Command):
    does = "Lint a qa_plan.py statically, without importing or running it."
    program = "ostler"
    argv = ("--full-ids", "qa", "lint", "plans/qa_plan.py")
    args = ARGS
    answers = (Exit(0, Lines(), "the plan passes"),)
    carries = act.LintPlan
    source = ("ostler/ostler/qa/lint.py", "ostler/ostler/qa/outcome.py")


class LintBadPlan(Command):
    does = "Refuse a plan that imports a module the plan language does not allow."
    program = "ostler"
    argv = ("--full-ids", "qa", "lint", "plans/bad/qa_plan.py")
    args = ARGS
    answers = (
        Exit(1, Lines(), "the plan breaks the lint, and each break is listed with its line"),
    )
    carries = act.LintBadPlan
    source = ("ostler/ostler/qa/lint.py",)


class ValidatePlan(Command):
    does = "Validate a qa_plan.py without running it: its scenarios, targets and the checks that back each obligation."
    program = "ostler"
    argv = ("--full-ids", "qa", "validate", "plans/qa_plan.py")
    args = ARGS
    answers = (Exit(0, Lines(), "the plan is valid"),)
    carries = act.ValidatePlan
    source = ("ostler/ostler/qa/plan.py", "ostler/ostler/qa/manifest.py", "ostler/ostler/qa/fixtures.py")


class ValidateBadPlan(Command):
    does = "Refuse to validate a plan the lint refuses."
    program = "ostler"
    argv = ("--full-ids", "qa", "validate", "plans/bad/qa_plan.py")
    args = ARGS
    answers = (
        Exit(1, Lines(), "the plan fails the lint, or a scenario claims coverage no check binds"),
    )
    carries = act.RunBadPlan
    source = ("ostler/ostler/qa/plan.py::load_plan",)


class RunPlan(Command):
    does = "Run a qa_plan.py in batch mode and write its ledger, its asserts, its evidence and its report beside it."
    program = "ostler"
    argv = ("--full-ids", "qa", "run", "plans/qa_plan.py")
    args = ARGS
    answers = (
        Exit(0, Lines(), "every assertion passed, and the line counts them"),
    )
    carries = act.RunPlan
    source = ("ostler/ostler/qa/run.py", "ostler/ostler/qa/harness_host.py", "ostler/ostler/qa/harness/ostler_qa.py",
              "ostler/ostler/qa/verdict.py", "ostler/ostler/qa/run_log.py", "ostler/ostler/qa/attribution.py",
              "ostler/ostler/qa/session.py", "ostler/ostler/util.py", "ostler/ostler/qa/v2.py",
              "ostler/ostler/qa/harness/ostler_qa_documents.py", "ostler/ostler/qa/harness/ostler_qa_files.py",
              "ostler/ostler/qa/harness/ostler_qa_scan.py", "ostler/ostler/qa/harness/ostler_qa_settle.py",
              "ostler/ostler/qa/harness/ostler_qa_transfer.py", "ostler/ostler/qa/harness/ostler_qa_verdicts.py",
              "ostler/ostler/qa/harness/ostler_qa_verifiers.py")


class RunBadPlan(Command):
    does = "Refuse to run a plan the lint refuses, and write nothing."
    program = "ostler"
    argv = ("--full-ids", "qa", "run", "plans/bad/qa_plan.py")
    args = ARGS
    answers = (
        Exit(1, Lines(), "the plan fails the lint, and the breaks are listed"),
    )
    carries = act.RunBadPlan
    source = ("ostler/ostler/qa/run.py::cmd_run",)


class ReportRun(Command):
    does = "Render the run per acceptance criterion and rewrite the report beside the plan."
    program = "ostler"
    argv = ("--full-ids", "qa", "report", "--spec", "plans")
    args = ARGS
    answers = (
        Exit(0, OPAQUE, "the report, which carries the times of the run"),
        Exit(1, Lines(), "the spec has no run log"),
    )
    carries = act.ReportRun
    source = ("ostler/ostler/qa/report.py", "ostler/ostler/qa/frames.py", "ostler/ostler/qa/stack.py")


class ReplayRun(Command):
    does = "Print a shell script that replays the steps of the run log."
    program = "ostler"
    argv = ("--full-ids", "qa", "replay", "--spec", "plans")
    args = ARGS
    answers = (
        Exit(0, OPAQUE, "the replay script"),
        Exit(1, Lines(), "the spec has no run log, and nothing is printed"),
    )
    carries = act.ReplayRun
    source = ("ostler/ostler/qa/session.py::cmd_replay",)


class ReadLedger(Command):
    does = "Print the flat, time-ordered listing of the run's ledger."
    program = "ostler"
    argv = ("--full-ids", "qa", "report", "--spec", "plans", "--ledger")
    args = ARGS
    answers = (
        Exit(0, OPAQUE, "the ledger, which carries the times of the run"),
        Exit(1, Lines(), "the spec has no run log"),
    )
    carries = act.ReadLedger
    source = ("ostler/ostler/qa/run_log.py",)


class CutFrames(Command):
    does = "Write the frames of a recording around a step."
    program = "ostler"
    argv = ("--full-ids", "qa", "frames", "--spec", "plans", "--step", "s1")
    args = ARGS
    answers = (Exit(1, Lines(), "the spec has no run log, or the run recorded nothing, which the sandbox never does"),)
    carries = act.CutFrames
    source = ("ostler/ostler/qa/frames.py::cmd_frames",)


class StartSession(Command):
    does = "Open a QA session in the spec folder and record its start in the ledger."
    program = "ostler"
    argv = ("--full-ids", "qa", "start", "RUN-2", "--story", "TST-01M585P7WKBH9YJ8E6NA73W4S9", "--spec", "plans")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the session is open"),
        Exit(1, Lines(), "a session is already open"),
    )
    carries = act.StartSession
    source = ("ostler/ostler/qa/session.py::cmd_start", "ostler/ostler/qa/addresses.py", "ostler/ostler/qa/devices.py")


class RecordStep(Command):
    does = "Run a command inside the open session and record it as a step."
    program = "ostler"
    argv = ("--full-ids", "qa", "step", "--id", "s1", "--label", "hello", "--mechanism", "fixture", "--cmd", "echo hi", "--spec", "plans")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the step is recorded"),
        Exit(1, Lines(), "no session is open"),
    )
    carries = act.RecordStep
    source = ("ostler/ostler/qa/session.py::cmd_step",)


class RecordAssertion(Command):
    does = "Run a named check inside the open session and record a pass or a fail."
    program = "ostler"
    argv = ("--full-ids", "qa", "assert", "--id", "a1", "--label", "status", "--check", "field_equal", "--spec", "plans",
            "actual=1", "expected=1")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the assertion passes"),
        Exit(1, Lines(), "no session is open"),
    )
    carries = act.RecordAssertion
    source = ("ostler/ostler/qa/session.py::cmd_assert", "ostler/ostler/qa/drivers.py", "ostler/ostler/qa/clean.py")


class StopSession(Command):
    does = "Close the open session and print how many assertions passed."
    program = "ostler"
    argv = ("--full-ids", "qa", "stop", "--spec", "plans")
    args = ARGS
    answers = (
        Exit(0, Lines(), "the session is closed"),
        Exit(1, Lines(), "no session is open"),
    )
    carries = act.StopSession
    source = ("ostler/ostler/qa/session.py::cmd_stop",)


class EnvRender(Command):
    does = "Write the compose file of the shared copy of the demo book's stack without starting it."
    program = "ostler"
    argv = ("--full-ids", "env", "render", "demo")
    args = ARGS
    answers = (Exit(0, Lines(), "the copy and the folder the compose file went to"),)
    carries = act.RenderStack
    source = ("ostler/ostler/environments/commands.py::cmd_render", "ostler/ostler/environments/render.py", "ostler/ostler/environments/runtime.py")


class EnvRenderUnknown(Command):
    does = "Refuse a book that has no ops/stack.yml, and list the books that have one."
    program = "ostler"
    argv = ("--full-ids", "env", "render", "nothing")
    args = ARGS
    answers = (Exit(1, STDERR, "no book has the name; the refusal is on standard error"),)
    carries = act.RenderUnknownBook
    source = ("ostler/ostler/environments/commands.py::cmd_render",)


class EnvDown(Command):
    does = "Stop the shared copy and delete the files rendered for it, or say it is not up."
    program = "ostler"
    argv = ("--full-ids", "env", "down")
    args = ARGS
    answers = (Exit(0, Lines(), "the copy is torn down, or was not up"),)
    carries = act.TearDownStack
    source = ("ostler/ostler/environments/commands.py::cmd_down", "ostler/ostler/environments/runtime.py")


class EnvAddress(Command):
    does = "Print the URL a copy publishes a name at, or say the copy publishes none."
    program = "ostler"
    argv = ("--full-ids", "env", "address", "demo-web")
    args = ARGS
    answers = (Exit(1, STDERR, "the shared copy is not up, so it publishes no address; the refusal is on standard error"),)
    carries = act.AddressOfDownStack
    source = ("ostler/ostler/environments/commands.py::cmd_address",)


class EnvExec(Command):
    does = "Run a command under the secrets the stack root names, which the sandbox names none of."
    program = "ostler"
    argv = ("--full-ids", "env", "exec", "--", "echo", "hi")
    args = ARGS
    answers = (Exit(0, Lines(), "the command's own output"),)
    carries = act.ExecUnderStack
    source = ("ostler/ostler/environments/commands.py::cmd_exec",)


class ValidateWebPlan(Command):
    does = "Validate a plan whose target is a browser, without running it or starting a browser."
    program = "ostler"
    argv = ("--full-ids", "qa", "validate", "plans/web/qa_plan.py")
    args = ARGS
    answers = (Exit(0, Lines(), "the plan is valid"),)
    carries = act.ValidatePlan
    source = ("ostler/ostler/qa/plan.py::validate_v2", "ostler/ostler/qa/harness/ostler_qa_browser.py",
              "ostler/ostler/qa/harness/ostler_qa_browser_state.py", "ostler/ostler/qa/harness/ostler_qa_dom.py")


class ValidatePhonePlan(Command):
    does = "Validate a plan whose target is a phone app, without running it or starting a device."
    program = "ostler"
    argv = ("--full-ids", "qa", "validate", "plans/phone/qa_plan.py")
    args = ARGS
    answers = (Exit(0, Lines(), "the plan is valid"),)
    carries = act.ValidatePlan
    source = ("ostler/ostler/qa/plan.py::validate_v2", "ostler/ostler/qa/android.py", "ostler/ostler/qa/maestro_sessions.py")


class RunWebPlan(Command):
    does = ("Refuse to run a browser plan before it starts anything, because the plan reads a secret the sandbox's environment lacks. "
            "A run that gets past the checks starts a browser and runs the scenarios, which the sandbox never does.")
    program = "ostler"
    argv = ("--full-ids", "qa", "run", "plans/web/qa_plan.py")
    args = ARGS
    answers = (
        Exit(0, OPAQUE, "every assertion passed in a browser"),
        Exit(1, OPAQUE, "the run is blocked, and each missing requirement of the machine is listed"),
    )
    carries = act.Examining
    source = ("ostler/ostler/qa/v2.py::run_plan", "ostler/ostler/qa/plan.py::check_runtime_requirements",
              "ostler/ostler/qa/harness/ostler_qa_elements.py", "ostler/ostler/qa/harness/ostler_qa_hierarchy.py")


class RunPhonePlan(Command):
    does = ("Refuse to run a phone plan before it starts anything, because the plan reads a secret the sandbox's environment lacks. "
            "A run that gets past the checks drives a device through Maestro, which the sandbox never does.")
    program = "ostler"
    argv = ("--full-ids", "qa", "run", "plans/phone/qa_plan.py")
    args = ARGS
    answers = (
        Exit(0, OPAQUE, "every assertion passed on a device"),
        Exit(1, OPAQUE, "the run is blocked, and each missing requirement of the machine is listed"),
    )
    carries = act.Examining
    source = ("ostler/ostler/qa/v2.py::run_plan", "ostler/ostler/qa/drivers.py")


class RunGrpcPlan(Command):
    does = ("Run a plan that calls a gRPC service nothing serves. The call fails, so the scenario and the run fail. "
            "A run against a live service passes.")
    program = "ostler"
    argv = ("--full-ids", "qa", "run", "plans/grpc/qa_plan.py")
    args = ARGS
    answers = (
        Exit(0, Lines(), "every call answered as the plan expects"),
        Exit(1, Lines(), "a call failed, and the line counts the assertions"),
    )
    carries = act.RunPlanWithoutTarget
    source = ("ostler/ostler/qa/harness/ostler_qa_grpc.py", "ostler/ostler/qa/harness/ostler_qa_responses.py",
              "ostler/ostler/qa/harness/ostler_qa_paths.py")


class VetWithoutArguments(Command):
    does = "Refuse a visual-fidelity check that names no screenshot, no manifest and no story, and print the usage."
    program = "ostler"
    argv = ("--full-ids", "vet")
    args = ARGS
    answers = (Exit(2, STDERR, "the arguments are required, and the usage is on standard error"),)
    carries = act.VetWithoutArguments
    source = ("ostler/ostler/cli.py::_cmd_vet",)


class VetWithoutRegions(Command):
    does = "Refuse a regions file that does not exist."
    program = "ostler"
    argv = ("--full-ids", "vet", "shot.png", "--manifest", "m.json", "--regions", "r.json", "--story", "TST-01M585P7WKBH9YJ8E6NA73W4S9")
    args = ARGS
    answers = (Exit(1, Lines(), "the regions file is not there"),)
    carries = act.VetWithoutRegions
    source = ("ostler/ostler/vet/regions.py", "ostler/ostler/vet/run.py")


class VetOfUnknownStory(Command):
    does = "Refuse a visual-fidelity check for a story id no story has."
    program = "ostler"
    argv = ("--full-ids", "vet", "shot.png", "--manifest", "m.json", "--regions", "r.json", "--story", "TST-NOPE")
    args = ARGS
    answers = (Exit(1, Lines(), "no story has the id"),)
    carries = act.VetOfUnknownStory
    source = ("ostler/ostler/vet/run.py::run_vet",)


class VetDryRun(Command):
    does = ("Check a screenshot against the regions the story's manifest declares, and print the report it would write. "
            "The sandbox's regions file lists none, so the check is clean, and the dry run writes nothing.")
    program = "ostler"
    argv = ("--full-ids", "vet", "shot.png", "--manifest", "vet/manifest.json", "--regions", "vet/regions.json", "--story",
            "TST-01M585P7WKBH9YJ8E6NA73W4S9")
    args = ARGS
    answers = (Exit(0, OPAQUE, "the report as a diff against the file it would write, and a note that --write was left out"),)
    carries = act.Reading
    source = ("ostler/ostler/vet/__init__.py", "ostler/ostler/vet/manifest.py", "ostler/ostler/vet/report.py",
              "ostler/ostler/vet/writes.py", "ostler/ostler/vet/geometry.py", "ostler/ostler/vet/crop.py",
              "ostler/ostler/vet/cdp.py", "ostler/ostler/vet/register.py")


class EnvUpUnknown(Command):
    does = ("Refuse to bring up a book that has no ops/stack.yml, before any container, lease or checkout is touched, "
            "and list the books that have one.")
    program = "ostler"
    argv = ("--full-ids", "env", "up", "nothing")
    args = ARGS
    answers = (Exit(1, STDERR, "no book has the name; the refusal is on standard error"),)
    carries = act.RenderUnknownBook
    source = ("ostler/ostler/environments/commands.py::cmd_up", "ostler/ostler/environments/leases.py",
              "ostler/ostler/environments/checkout.py")


ALL = (
    Doctor, ListEpicRows, ListStoryRows, SearchPlan, BuildIndex, QueryCovering, NextEpic, NextStory, ShowChecks, EvictCache,
    EditRename, EditRenameUnknown, CreateMilestone, MilestoneEpicsFirst, MilestoneEpicsBoth, MilestoneEpicsUnknown,
    MilestoneSourceItem, CreateSpec, CreateSpecOfUnknownStory, BacklogAdd, BacklogList, BacklogPrune, BacklogDropWithoutReason,
    FileDecision, TemplateNew, TemplateFind, TemplateApply, TemplateDelete, ListArtifactKinds, ScaffoldArtifact, VetArtifact,
    CleanQaScratch, EnvSchema, EnvCheck, EnvList, EnvListAll, EnvPrune, BacklogAdopt, LintPlan, LintBadPlan, ValidatePlan,
    ValidateBadPlan, RunPlan, RunBadPlan, ReportRun, ReplayRun, ReadLedger, CutFrames, StartSession, RecordStep, RecordAssertion,
    StopSession, EnvRender, EnvRenderUnknown, EnvDown, EnvAddress, EnvExec,
    ValidateWebPlan, ValidatePhonePlan, RunWebPlan, RunPhonePlan, RunGrpcPlan, VetWithoutArguments, VetWithoutRegions,
    VetOfUnknownStory, VetDryRun, EnvUpUnknown,
)
