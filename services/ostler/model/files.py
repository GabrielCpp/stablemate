"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

from ostler.book import Mark, Watched

from ..fixtures import EPICS, STORY_PATHS

NOT_STARTED = "status: Not started"
IN_PROGRESS = "status: in-progress"
BLOCKED = "status: 'Blocked: waiting'"
DONE = "status: Done"
CAPITAL = "status: In progress"
STATUS_LINES = {"Not started": NOT_STARTED, "in-progress": IN_PROGRESS, "In progress": CAPITAL, "Blocked: waiting": BLOCKED,
                "Done": DONE}
BULLET_LINES = {name: f"- **Status**: {name}" for name in STATUS_LINES}
CONFLICT_TEXTS = ("criteria disagree", "specs contradict")
CONFLICT_LINES = tuple(f"conflict: {t}" for t in CONFLICT_TEXTS)
SEED_IDS = ("SD-3", "SD-4")
SEED_STATUSES = ("backlog", "researched")
SEED_LAYERS = (None, "frontend")


def seed_block(seed_id: str, status: str, layer: str | None) -> str:
    """The block `seed add` leaves under Seeds: heading, status line, the layers line when there is one, a blank line."""
    layers = f"- layers: {layer}\n" if layer else ""
    return f"### {seed_id}\n- status: {status}\n{layers}\n"


DEPENDENCY_LINES = tuple(f"- Blocked by: {slug}" for slug in ("alpha", "bravo"))
STORY_HEADINGS = tuple(f"### {slug}" for slug in ("alpha", "bravo", "sx", "delta"))
TITLE_LINES = tuple(f"- title: {head} {slug}" for slug in ("alpha", "bravo", "sx") for head in ("Story", "Renamed")) + (
    "- title: Delta story",)
COVER_LINES = ("- covers: SD-3", "- covers: SD-4")

MILESTONE = "docs/milestones/0001-ms/milestone.md"
PROPOSED = "status: proposed"
FIRST_EPIC_LISTED = "1. First epic (`TST-01M585P778TKS9VRC0053BQDSZ`, `0001-first`)"
SECOND_EPIC_LISTED = "2. Second epic (`TST-01M585PEGMRE3FWETV74QRSSY3`, `0002-second`)"
SOURCE_ITEM = "sourceItems:\n- SD-3"
RECORD_ID = "TST-01M7N888KSZ21DR28M6BSGQTY2"
RECORD = f"art/backlogs/acme/web/{RECORD_ID}/record.md"
OPEN = "status: open"
CLOSED = "status: done"
DECISION = "docs/decisions/use-x/decision.md"
ACCEPTED = "status: accepted"
SPEC = "art/specs/TST-01M585P7WKBH9YJ8E6NA73W4S9/plan.md"
SPEC_TYPE = "type: spec.plan"
ARTIFACT = "art/specs/TST-01M585P7WKBH9YJ8E6NA73W4S9/plan-context.json"
ORDER_KEY = '"implementation_order"'
TEMPLATES = ".agents/templates.yml"
TEMPLATE_DECLARED = "tpl:\n  title: tpl"
GUIDANCE = "CLAUDE.md"
GUIDED = "<!-- ostler:template:tpl:start -->"

OLD_LIST = "old-backlog.md"
OLD_BULLET = "- [OLD-1] Tidy the thing"
OLD_RECORDS = {"OLD-1": "Tidy the thing", "OLD-2": "Rename the other"}
RENDERED = "home/.local/state/stablemate/ostler/environments/plan-shared/compose.yml"
SESSION = "plans/qa/qa-session.json"
ASSERTED = '"assert_count": 1'
PASSED = '"pass_count": 1'
LEDGER = "plans/qa/qa-run.ndjson"
QA_REPORT = "plans/qa-report.md"
QA_EVIDENCE = "plans/qa-evidence.json"
RAN_ASSERT = "plans/qa/asserts/adds-up-1.json"
STEP_ASSERT = "plans/qa/asserts/a1.json"

SEED_BLOCKS = tuple(seed_block(i, s, layer) for i in SEED_IDS for s in SEED_STATUSES for layer in SEED_LAYERS)

MARKS = (
    Mark("art/epics/*/stories/*/story.md", *STATUS_LINES.values(), *BULLET_LINES.values(), *CONFLICT_LINES,
         *DEPENDENCY_LINES),
    Mark(OLD_LIST, OLD_BULLET),
    Mark(SESSION, ASSERTED, PASSED),
    Mark(RENDERED),
    Mark(LEDGER),
    Mark(QA_REPORT),
    Mark(QA_EVIDENCE),
    Mark("plans/qa/asserts/*.json"),
    Mark(MILESTONE, PROPOSED, FIRST_EPIC_LISTED, SECOND_EPIC_LISTED, SOURCE_ITEM),
    Mark("art/backlogs/*/record.md", OPEN, CLOSED),
    Mark(DECISION, ACCEPTED),
    Mark(SPEC, SPEC_TYPE),
    Mark(ARTIFACT, ORDER_KEY),
    Mark(TEMPLATES, TEMPLATE_DECLARED),
    Mark(GUIDANCE, GUIDED),
    Mark("art/epics/*/epic.md", *SEED_BLOCKS, *STORY_HEADINGS, *TITLE_LINES, *COVER_LINES),
)

EPIC_PATHS = tuple(f"art/epics/{e}/epic.md" for e in EPICS)
STORY_FILES = tuple(STORY_PATHS.values())


class FileRecord(Watched):
    """A watched file the sandbox holds."""

    marks = MARKS
    source = ("ostler/ostler/crud.py", "ostler/ostler/markdown.py")


def holding(path: str, *strings: str) -> FileRecord:
    """The record of a file that holds these strings, in the order the watch lists them."""
    return FileRecord.holding(path, *strings)
