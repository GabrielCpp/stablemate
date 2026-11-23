"""What the commands that carry their words in the argv do to the documents they write: the milestone, the Register's
record, the decision, the spec, the artifact and the template. Each refusal is the line the tool prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Delete, Exited, Rule, Transaction, Update

from ..fixtures import Nothing
from .files import (ACCEPTED, ARTIFACT, ASSERTED, CLOSED, DECISION, FIRST_EPIC_LISTED, GUIDANCE, GUIDED, LEDGER, MILESTONE, OLD_LIST,
                    OLD_RECORDS, OPEN, ORDER_KEY, PASSED, PROPOSED, QA_EVIDENCE, RENDERED, QA_REPORT, RAN_ASSERT, RECORD, RECORD_ID,
                    SECOND_EPIC_LISTED, SESSION, SOURCE_ITEM, SPEC, SPEC_TYPE, STEP_ASSERT, TEMPLATE_DECLARED, TEMPLATES,
                    FileRecord)
from .state import Plan

FAILED = Exited(1)
SANDBOX_ARTIFACT = f"<sandbox>/{ARTIFACT}"
SANDBOX_DECISION = f"<sandbox>/{DECISION}"


def _present(path: str):
    return lambda a, s, by: path in s.files.items


def _absent(path: str):
    return lambda a, s, by: path not in s.files.items


def _always(a: Nothing, s: Plan, by: Actor | None) -> bool:
    return True


def holds(s: Plan, path: str) -> tuple[str, ...]:
    return s.files[path].holds if path in s.files.items else ()


def keep(s: Plan, path: str, *strings: str) -> Create | Update:
    """The change that leaves this file holding exactly these strings, made if it was not there."""
    record = FileRecord.holding(path, *strings)
    return Update(s.files, path, record) if path in s.files.items else Create(s.files, record)


milestone_exists = Rule[Nothing, Plan]("milestone '0001-ms' already exists", _present(MILESTONE), FAILED)
no_milestone = Rule[Nothing, Plan]("no milestone 'ms'", _absent(MILESTONE), FAILED)
no_such_epic = Rule[Nothing, Plan]("milestone '0001-ms' keeps its epics: 'nope' names no epic", _always, FAILED)
unknown_story_for_spec = Rule[Nothing, Plan]("no story with id 'TST-NOPE'", _always, FAILED)
no_old_list = Rule[Nothing, Plan](f"no list at <sandbox>/{OLD_LIST}", _absent(OLD_LIST), FAILED)
record_taken = Rule[Nothing, Plan](f"record id '{RECORD_ID}' is already taken", _present(RECORD), FAILED)
no_record = Rule[Nothing, Plan](f"no record '{RECORD_ID}'", _absent(RECORD), FAILED)
reason_needed = Rule[Nothing, Plan]("--as dropped requires --reason", _always, FAILED)
decision_exists = Rule[Nothing, Plan](
    f"decision 'use-x' already exists at {SANDBOX_DECISION}: read it, or pick a different slug", _present(DECISION), FAILED)
template_exists = Rule[Nothing, Plan]("template 'tpl' already exists", lambda a, s, by: TEMPLATE_DECLARED in holds(s, TEMPLATES), FAILED)
no_template = Rule[Nothing, Plan]("no template 'tpl'", lambda a, s, by: TEMPLATE_DECLARED not in holds(s, TEMPLATES), FAILED)
artifact_exists = Rule[Nothing, Plan](
    f"error: {SANDBOX_ARTIFACT} already exists (pass --force to overwrite)", _present(ARTIFACT), FAILED)
artifact_missing = Rule[Nothing, Plan](
    f"error: {SANDBOX_ARTIFACT} does not exist — scaffold it first", _absent(ARTIFACT), FAILED)
artifact_unfilled = Rule[Nothing, Plan](
    "plan-context: problems\n  - implementation_order entry '<repo>::<path>' matches no declared service "
    "(declared: ['<workspace repo name>::<service dir, e.g. api or web>']).",
    _present(SPEC), FAILED)
artifact_without_plan = Rule[Nothing, Plan](
    "plan-context: problems\n  - services[0]: plan_file 'plan.md' not found in <sandbox>/art/specs/TST-01M585P7WKBH9YJ8E6NA73W4S9.\n"
    "  - implementation_order entry '<repo>::<path>' matches no declared service "
    "(declared: ['<workspace repo name>::<service dir, e.g. api or web>']).",
    _absent(SPEC), FAILED)


def relist(s: Plan, dropped: tuple[str, ...], *listed: str) -> Create | Update:
    """The change that leaves the milestone holding what it held, less these strings, and these listed."""
    kept = tuple(h for h in holds(s, MILESTONE) if h not in dropped)
    return keep(s, MILESTONE, *kept, *listed)


EPICS = (FIRST_EPIC_LISTED, SECOND_EPIC_LISTED)


def set_epics(s: Plan, *listed: str) -> Transaction:
    return Transaction(relist(s, EPICS, *listed), says=(f"set {len(listed)} epic(s) on milestone '0001-ms'",))


class MakeMilestone(Action[Nothing, Plan]):
    accept = Nothing
    rules = (milestone_exists,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, MILESTONE, PROPOSED), says=())


class ListFirstEpic(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_milestone,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return set_epics(s, FIRST_EPIC_LISTED)


class ListBothEpics(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_milestone,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return set_epics(s, *EPICS)


class ListUnknownEpic(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_milestone, no_such_epic)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class OwnSourceItem(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_milestone,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(relist(s, (SOURCE_ITEM,), SOURCE_ITEM), says=("set 1 source item(s) on milestone '0001-ms'",))


class TypeSpec(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        name = "spec 'TST-01M585P7WKBH9YJ8E6NA73W4S9/plan.md'"
        if SPEC in s.files.items:
            return Transaction(says=(f"{name} already typed (spec.plan)",))
        return Transaction(keep(s, SPEC, SPEC_TYPE), says=(f"created {name} (spec.plan)",))


class TypeSpecOfUnknownStory(Action[Nothing, Plan]):
    accept = Nothing
    rules = (unknown_story_for_spec,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class FileRecordOfWork(Action[Nothing, Plan]):
    accept = Nothing
    rules = (record_taken,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, RECORD, OPEN), says=(f"filed record '{RECORD_ID}'",))


class ListRecords(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        shelf = sorted(f.path for f in s.files if f.path.startswith("art/backlogs/"))
        if not shelf:
            return Transaction(says=("(none)",))
        lines = []
        for path in shelf:
            _, _, _, area, ident, _ = path.split("/")
            status = "done" if CLOSED in holds(s, path) else "open"
            lines.append(f"{ident}\tacme\t{area}\t{status}\tuntriaged\t{OLD_RECORDS.get(ident, 'Fix thing')}")
        return Transaction(says=tuple(lines))


class AdoptList(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_old_list,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        made = [Create(s.files, FileRecord.holding(f"art/backlogs/acme/general/{ident}/record.md", OPEN)) for ident in OLD_RECORDS]
        lines = tuple(f"{ident}\tacme\tgeneral\topen\tuntriaged\t{text}" for ident, text in OLD_RECORDS.items())
        return Transaction(Delete(s.files, OLD_LIST), *made, says=(*lines, "imported 2 records, kept 2 ids"))


class CloseRecord(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_record,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        if CLOSED in holds(s, RECORD):
            return Transaction(says=(f"record '{RECORD_ID}' is already done",))
        return Transaction(keep(s, RECORD, CLOSED), says=(f"closed record '{RECORD_ID}' as done",))


class DropRecordWithoutReason(Action[Nothing, Plan]):
    accept = Nothing
    rules = (reason_needed,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class FileDecision(Action[Nothing, Plan]):
    accept = Nothing
    rules = (decision_exists,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, DECISION, ACCEPTED), says=(SANDBOX_DECISION,))


class DeclareTemplate(Action[Nothing, Plan]):
    accept = Nothing
    rules = (template_exists,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, TEMPLATES, TEMPLATE_DECLARED), says=("created template 'tpl' (1 kind(s))",))


class ShowTemplate(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ApplyTemplate(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_template,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, GUIDANCE, GUIDED), says=("applied template 'tpl' (1 dir(s) scaffolded)",))


class DeleteTemplate(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_template,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, TEMPLATES), says=("deleted template 'tpl'",))


class ScaffoldArtifact(Action[Nothing, Plan]):
    accept = Nothing
    rules = (artifact_exists,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, ARTIFACT, ORDER_KEY), says=(f"scaffolded plan-context -> {SANDBOX_ARTIFACT}",))


class VetArtifact(Action[Nothing, Plan]):
    accept = Nothing
    rules = (artifact_missing, artifact_unfilled, artifact_without_plan)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class Reading(Action[Nothing, Plan]):
    """A command that reads the plan and changes no file."""

    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class Examining(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class CountEnvServices(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("1 services in 1 books fit together",))


class ListEnvServices(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("demo", "  demo:web  a static page server  demo-web :18080"))


class ListEveryCopy(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        listed = "<sandbox>/plan  shared  unknown  stopped  age 0m  unused unknown"
        return Transaction(says=(listed if RENDERED in s.files.items else "no copy exists on this machine",))


class PruneNothing(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("nothing to prune",))


class EvictCache(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("removed 0 aged-out entries from <sandbox>/index",))


class RenameUnknownSlug(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("error: slug 'nothing' not found", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


LINT_FAILED = (
    "Plan lint failed:\n  - line 1: `import os` is not allowed — the allowed modules are: collections, dataclasses, datetime, "
    "enum, hashlib, itertools, json, ostler, ostler.qa, ostler_qa, re, textwrap, typing")
LEDGER_PATH = f"<sandbox>/{LEDGER}"
SESSION_PATH = f"<sandbox>/{SESSION}"

plan_does_not_lint = Rule[Nothing, Plan](LINT_FAILED, _always, FAILED)
report_without_run = Rule[Nothing, Plan](
    f"error: qa report: the run log is missing at {LEDGER_PATH} — has this spec been run?", _absent(LEDGER), FAILED)
replay_without_run = Rule[Nothing, Plan]("", _absent(LEDGER), FAILED)
ledger_without_run = Rule[Nothing, Plan](f"error: run log not found: {LEDGER_PATH}", _absent(LEDGER), FAILED)
frames_without_run = Rule[Nothing, Plan](
    f"error: qa frames: the run log is missing at {LEDGER_PATH} — has this spec been run?", _absent(LEDGER), FAILED)
frames_without_recording = Rule[Nothing, Plan]("error: qa frames: this run has no recording", _always, FAILED)
no_session = Rule[Nothing, Plan](
    f"No open QA session at {SESSION_PATH}. Run `ostler qa start` first.", _absent(SESSION), FAILED)
session_open = Rule[Nothing, Plan](
    f"A QA session is already open at {SESSION_PATH}. Run `ostler qa stop` first.", _present(SESSION), FAILED)


def add(s: Plan, path: str, *strings: str) -> Create | Update:
    """The change that leaves this file holding what it held and these strings too."""
    return keep(s, path, *holds(s, path), *strings)


class LintPlan(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("Plan lint passed.",))


class LintBadPlan(Action[Nothing, Plan]):
    accept = Nothing
    rules = (plan_does_not_lint,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ValidatePlan(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("Plan is valid.",))


class RunPlan(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        made: list[Create | Update | Delete] = [keep(s, LEDGER), keep(s, QA_REPORT), keep(s, QA_EVIDENCE), keep(s, RAN_ASSERT)]
        if SESSION in s.files.items:
            made.append(Delete(s.files, SESSION))
        return Transaction(*made, says=("QA run PASSED: 1 assertions passed, 0 failed, 1 scenarios",))


class RunBadPlan(Action[Nothing, Plan]):
    accept = Nothing
    rules = (plan_does_not_lint,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ReportRun(Action[Nothing, Plan]):
    accept = Nothing
    rules = (report_without_run,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, QA_REPORT), says=())


class ReplayRun(Action[Nothing, Plan]):
    accept = Nothing
    rules = (replay_without_run,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ReadLedger(Action[Nothing, Plan]):
    accept = Nothing
    rules = (ledger_without_run,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class CutFrames(Action[Nothing, Plan]):
    accept = Nothing
    rules = (frames_without_run, frames_without_recording)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class StartSession(Action[Nothing, Plan]):
    accept = Nothing
    rules = (session_open,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(keep(s, SESSION), keep(s, LEDGER),
                           says=("QA session started: run_id=RUN-2, story=TST-01M585P7WKBH9YJ8E6NA73W4S9",))


class RecordStep(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_session,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("step 's1' recorded",))


class RecordAssertion(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_session,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(add(s, SESSION, ASSERTED, PASSED), keep(s, STEP_ASSERT), says=("assert 'a1': PASS",))


class StopSession(Action[Nothing, Plan]):
    accept = Nothing
    rules = (no_session,)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        passed = 1 if PASSED in holds(s, SESSION) else 0
        return Transaction(Delete(s.files, SESSION), says=(f"QA run complete: PASS ({passed} passed, 0 failed, 0 steps)",))


class CheckBook(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("check: 0 findings",))


class IndexBook(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("<sandbox>/services/demo/index.tsv: unchanged",))


class ListBookDecisions(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("say-hello (story none, 2026-11-17): The demo book greets with the word hello and nothing else.",))


class ExplainNothing(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("nothing in demo is called 'Nope'; try `search services.demo Nope`", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


UNMOVED = (
    "error: <sandbox>/unmoved holds an ostler book, and the book now lives in the artifacts folder. "
    "Either keep it beside the code by setting `book: {home: repo}` in <sandbox>/unmoved/agents.yml, "
    "or move the book to <sandbox>/art following docs/guide/moving-a-book-to-the-artifacts-folder.md."
)


class SearchUnmovedBook(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan](UNMOVED, _always, Exited(2)),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class MoveBook(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("moved services/flat to services/acme/flat", "rewrote 1 reference(s) in services/acme/flat/owner.py"))


class RenderStack(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        where = "<sandbox>/home/.local/state/stablemate/ostler/environments/plan-shared"
        return Transaction(keep(s, RENDERED), says=(f"rendered shared into {where}",))


class RenderUnknownBook(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("no book is named `nothing` (books with an ops/stack.yml: demo)", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ListUnknownRepo(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("error: no repo 'nothing' here: pass this repo's name or an id prefix, one of TST", _always, Exited(2)),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ResetUnknownCopy(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("no copy named nothing is up: bring it up with ostler env up", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class TearDownStack(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        if RENDERED not in s.files.items:
            return Transaction(says=("shared is not up",))
        return Transaction(Delete(s.files, RENDERED), says=("tore shared down",))


class AddressOfDownStack(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("shared publishes no `demo-web` (it publishes none, since it is not up)", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class ExecUnderStack(Action[Nothing, Plan]):
    accept = Nothing

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction(says=("hi",))


VET_USAGE = (
    "usage: ostler vet [-h] [--write] --manifest MANIFEST\n"
    "                  (--cdp-url CDP_URL | --regions REGIONS_FILE) --story STORY\n"
    "                  [--state STATE] [--iou-threshold IOU_THRESHOLD] [--json]\n"
    "                  [--no-index] [--index-dir DIR]\n"
    "                  screenshot\n"
    "ostler vet: error: the following arguments are required: screenshot, --manifest, --story")


class VetWithoutArguments(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan](VET_USAGE, _always, Exited(2)),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class VetWithoutRegions(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("error: regions file 'r.json' does not exist", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class VetOfUnknownStory(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("error: no story with id 'TST-NOPE'", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()


class RunPlanWithoutTarget(Action[Nothing, Plan]):
    accept = Nothing
    rules = (Rule[Nothing, Plan]("QA run FAILED: 0 assertions passed, 1 failed, 1 scenarios", _always, FAILED),)

    @staticmethod
    def reduce(a: Nothing, s: Plan, by: Actor | None) -> Transaction:
        return Transaction()
