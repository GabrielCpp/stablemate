"""The dev flow's models: plan, path validation, dispatch, implement, gate, fix."""
from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator

from workhorse_workflows.coder.shared.schemas._base import CoderResult, Finding


ImplStatus = Literal["done", "applied", "no_changes_needed", "needs_changes", "blocked"]


class PlanService(CoderResult):
    """One service the plan changes: where it lives, what it is, what to read, what to do."""

    repo: str = Field(
        default="", description="The workspace repo this service lives in."
    )
    path: str = Field(
        default="",
        description="Path from that repo's root to the service directory; `.` for a "
        "repo-root service.",
    )
    type: str = Field(
        default="",
        description="The technology key this repo gates its skills and prompts on. Read it "
        "out of the repo's own `agents.yml` rather than naming a taxonomy from memory.",
    )
    plan_file: str = Field(
        default="",
        description="The per-service plan file you wrote, relative to the spec dir. Blank "
        "on a shared package, which has no plan of its own.",
    )
    new_service: bool = Field(
        default=False,
        description="True when the directory does not exist yet and implementation will "
        "scaffold it, which is what waives the path and marker checks for this entry.",
    )


FIXTURE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")


def lift_fixture(item: str) -> dict[str, str]:
    """A bare string as a fixture: its name if it is a key, otherwise what it promises."""
    if FIXTURE_KEY.match(item):
        return {"name": item}
    return {"name": "", "provides": item}


class PlanFixture(CoderResult):
    """One arrangement the story's QA lane stands up before it observes anything."""

    name: str = Field(
        default="",
        description="The fixture's key, as `qa.fixture()` spells it — resolved against the "
        "repo's `agents.yml` `qa:` block, which is where the command itself lives.",
    )
    provides: str = Field(
        default="",
        description="The state this fixture guarantees once it has run, in the words a "
        "scenario can assert against.",
    )


class PlanResult(CoderResult):
    """What every plan turn returns — `plan-story`, `repair-plan-paths`, `replan-with-answer`."""

    status: Literal["done", "blocked"] = Field(
        description="`done` when the plan artifacts are written and ready for review, "
        "including when they were already there and you left them standing. `blocked` when "
        "you could not produce a plan at all.",
    )
    summary: str = Field(
        default="",
        description="One line describing the plan — or, when blocked, the blocker.",
    )

    services: list[PlanService] = Field(
        default=[],
        description="Every service this story changes, one entry each. This is the only "
        "place the workflow learns which services the story touches, and it drives the "
        "implementer's per-service iteration: a frontend-only story lists only its web "
        "service. A story that changes exactly one service in one repo may return `[]` — "
        "the implementer then gets one repo-root layer.",
    )
    implementation_order: list[str] = Field(
        default=[],
        description="Build order as `repo::path` keys: whatever defines a contract before "
        "whatever implements it, and that before whatever consumes it.",
    )
    shared_packages: list[PlanService] = Field(
        default=[],
        description="Non-service directories — libraries, shared code — the plan also "
        "changes. Same shape as a service, with no `plan_file`.",
    )
    verification_setup: dict[str, Any] = Field(
        default={},
        validation_alias=AliasChoices("verification_setup", "qa_stack"),
        description="The story's `## Verification setup`, machine-readable: the `profile` "
        "that renders this surface with realistic data, and what that stack is "
        "`capable_of_rendering` — the surface it can actually show, not a thin default.",
    )
    fixtures: list[PlanFixture] = Field(
        default=[],
        description="The fixtures this story's QA lane needs, typed out of the block above. "
        "The prose there stays prose; this list is the part a later lane acts on.",
    )

    @model_validator(mode="before")
    @classmethod
    def _lift_declared_fixtures(cls, data: Any) -> Any:
        """A `fixtures:` list nested in `## Verification setup` is the story's fixture list."""
        if not isinstance(data, dict) or data.get("fixtures") is not None:
            return data
        setup = data.get("verification_setup") or data.get("qa_stack") or {}
        nested = setup.get("fixtures") if isinstance(setup, dict) else None
        if isinstance(nested, list):
            return {
                **data,
                "fixtures": [
                    lift_fixture(item) if isinstance(item, str) else item
                    for item in nested
                ],
            }
        return data

    @field_validator("fixtures", mode="before")
    @classmethod
    def _lift_bare_fixtures(cls, v: Any) -> Any:
        """A bare string in the typed list gets the same reading as one in the nested one."""
        if isinstance(v, list):
            return [lift_fixture(item) if isinstance(item, str) else item for item in v]
        return v

    @field_validator("shared_packages", mode="before")
    @classmethod
    def _lift_bare_paths(cls, v: Any) -> Any:
        """A bare string in `shared_packages` is the directory it names."""
        if isinstance(v, list):
            return [{"path": item} if isinstance(item, str) else item for item in v]
        return v


class ImplResult(CoderResult):
    """`<flow>/prompts/implement-plan.md` — one service layer implemented, or the blocker."""

    status: ImplStatus = Field(
        description="`done` only when the implementation is complete, verification passed "
        "and the touched layers were smoked. `applied` when the repair asked for is written "
        "and exercised. `no_changes_needed` when the item was already fixed in the tree. "
        "`needs_changes` when you got part of the way and the rest is still open. `blocked` "
        "when you could not complete it or could not run it locally. There is no blank "
        "answer: a turn that cannot name one of these has not reported, and it is retried.",
    )
    notes: str = Field(
        default="",
        description="What you implemented and verified, including how you ran it locally "
        "and what you observed — or, when blocked, the blocker.",
    )


class FailureReport(CoderResult):
    """A gate said no."""

    source: str = ""
    command: str = ""
    cwd: str = ""
    output: str = ""
    findings: list[Finding] = []
    lap: int = 0

    @property
    def digest(self) -> str:
        """A stable fingerprint of *this failure*, for detecting a stalled loop."""
        material = "\n".join(
            (self.source, self.command, " ".join(self.output.split()))
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:12]


class FixResult(CoderResult):
    """`dev/prompts/dev-fix.md` — the repair turn's own report, whatever the gate was."""

    status: Literal["fixed", "failed", "blocked"] = Field(
        description="`fixed` — the gate passes now in this directory. `failed` — findings "
        "remain, but another lap over the same output could plausibly close them. "
        "`blocked` — no lap of this stage can make the gate pass: the command does not run "
        "here at all, the fix demands a behaviour change this stage may not make, or it "
        "lives in a repo you were not given. This ends the laps and hands the block to "
        "whoever can decide it; it is not a way to stop trying.",
    )
    notes: str = Field(
        default="",
        description="What you changed — or, when a finding remains, which one and why. On "
        "`blocked`, say specifically which of the three cases above applies.",
    )


class OperatorResolution(CoderResult):
    """`shared/prompts/resolve-operator.md` — the resolver's report on a block."""

    decision: Literal["answered", "escalated"] = Field(
        description="`answered` only when you can quote something already written that "
        "settles the question, and you have written the answer down. `escalated` for "
        "everything else, including when you are not sure.",
    )

    summary: str = Field(
        default="", description="One line: what was decided, or what is blocking."
    )

    grounded: list[str] = Field(
        default=[],
        description="One line per source that determined an `answered` decision — "
        "`file:line`, and the rule quoted from it. Must be non-empty when you answer: it "
        "is what lets an operator check your work later without redoing it. Empty when "
        "you escalate.",
    )

    record: str = Field(
        default="",
        description="The decision-record slug you wrote, or the one you cited. Empty when "
        "escalating.",
    )

    tried: list[str] = Field(
        default=[],
        description="What you investigated and ruled out, one concrete line each: the "
        "command you ran and what it printed, the file you read and what it said, the "
        "hypothesis you tested and why it was wrong. When you escalate this is published "
        "verbatim in the gate a human reads — without it they re-run every dead end you "
        "already paid for.",
    )


class OperatorGate(CoderResult):
    """The escalation body a flow hands to `Await` — see `coder.shared.escalation`."""

    body: str = ""
    number: int = 0


class OperatorAnswer(CoderResult):
    """What `<story-folder>/context.md` said once the operator (or the resolver) answered."""

    answered: bool = False
    scope: Literal["story", "epic"] = "story"
    content: str = ""


class PlanValidation(CoderResult):
    """`record_plan` — the projection Python wrote, and whether it points at real services."""

    status: Literal["valid", "invalid"] = "valid"
    errors: list[str] = []
    document: dict[str, Any] = {}


class DispatchEntry(CoderResult):
    """One service to implement: where it lives, what type it is, how to verify it."""

    service: str = ""
    repo: str = ""
    cwd: str = ""
    service_path: str = ""
    type: str = ""
    plan_file: str = ""
    qa_mode: str = ""
    qa_skills: list[str] = []
    verification: str = ""
    label: str = ""


class StorySource(CoderResult):
    """One story-scoped source root with its repository provenance."""

    repo: str = ""
    checkout: str = ""
    surface: str = ""
    root: str = "."
    base: str = ""
    head: str = "WORKTREE"


class StorySources(CoderResult):
    """Multi-repository source context derived from exact story commit trailers."""

    status: Literal["valid", "invalid"] = "valid"
    sources: tuple[StorySource, ...] = ()
    errors: tuple[str, ...] = ()


class QaRunEntry(CoderResult):
    """One service's QA brief, derived from its dispatch entry."""

    service: str = ""
    label: str = ""
    qa_mode: str = ""
    qa_skill: str = ""
    qa_skills: list[str] = []


class PlanSummary(CoderResult):
    """The plan's structure as prose, for a turn in a lane that did not produce it."""

    text: str = ""


class ImplContext(CoderResult):
    """`resolve_impl_context` — the approved plan decoded against the workspace."""

    qa_run_plan: list[QaRunEntry] = []
    verification_setup: dict[str, Any] = {}
    fixtures: list[PlanFixture] = []
    shared_packages: list[str] = []
    dispatch_list: list[DispatchEntry] = []
    affected_repos: list[str] = []
    affected_repo_paths: list[str] = []
    qa_source_roots: list[str] = []

    @property
    def dispatch_count(self) -> int:
        """The YAML's `dispatch_count` output — `len(dispatch_list)` stringified."""
        return len(self.dispatch_list)


class BranchOutcome(CoderResult):
    """`branch-code-repos.py` — which code repos moved onto the story branch."""

    branched: list[str] = []
    already_on_branch: list[str] = []


class LayerPick(CoderResult):
    """`select-next-layer.py` — the next service to implement, or "the list is exhausted"."""

    has_layer: bool = False
    index: int = -1
    layer: DispatchEntry = DispatchEntry()
    dispatch_count: int = 0


class GateOutcome(CoderResult):
    """`run_gate` — one of a service's declared gate commands and what it said."""

    gate: str = ""
    status: Literal["clean", "dirty", "skipped"] = "skipped"
    command: str = ""
    output: str = ""
    reason: str = ""


class StoryStatusCheck(CoderResult):
    """`check_story_status` — whether the story's Status line still says what it may."""

    status: Literal["clean", "dirty"] = "dirty"
    written: str = ""


class GateList(CoderResult):
    """`declared_gates` — the commands that will run after the turn being briefed."""

    gates: list[str] = []
    commands: list[str] = []
    text: str = ""


class Lap(CoderResult):
    """Where the repair loop is, as one state parameter."""

    fix_lap: int = 0
    session_turns: int = 1
    digest: str = ""


class ChangedFiles(CoderResult):
    """What this story has already written into one service, by path."""

    paths: list[str] = []


class DevResult(CoderResult):
    """What the dev flow hands back: `ready`, or `replan` when the epic premise was wrong."""

    status: Literal["ready", "replan"] = "ready"
    operator_notes: str = ""
    session_turns: int = 0


__all__ = [
    "BranchOutcome",
    "ChangedFiles",
    "DevResult",
    "DispatchEntry",
    "FailureReport",
    "FixResult",
    "ImplContext",
    "ImplResult",
    "ImplStatus",
    "GateList",
    "GateOutcome",
    "Lap",
    "LayerPick",
    "OperatorAnswer",
    "OperatorGate",
    "OperatorResolution",
    "PlanResult",
    "PlanValidation",
    "QaRunEntry",
    "StoryStatusCheck",
]
