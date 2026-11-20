"""The book lane's models: the seat's verdict, and what each play of the book returns."""
from __future__ import annotations

from typing import Literal

from pydantic import Field
from workhorse.pyflow import dry_run

from workhorse_workflows.coder.shared.schemas._base import CoderResult
from workhorse_workflows.coder.shared.schemas.qa import QaFinding
from workhorse_workflows.kit.result import Result


class ServiceCalls(Result):
    """The calls of one service the story's claims bear on."""

    service: str = Field(description="The service's name, as the folder under `services/` spells it.")
    calls: list[str] = Field(
        default=[],
        description="The calls of that service the story's claims bear on, by the name the book "
        "gives them.",
    )


@dry_run(status="passed")
class BookQaOwnerResult(CoderResult):
    """`book_qa/prompts/qa-book.md`: the book seat's verdict on its story."""

    status: Literal["passed", "findings", "blocked"] = Field(
        description="`passed` when every claim a call can show is stated by the book and the "
        "targeted run of the touched calls exits 0 with nothing for the developer to fix. "
        "`findings` when the app does not do what a claim says, and each such claim is one entry "
        "in `findings`. `blocked` only when the base run was red or the environment was not "
        "healthy: repair nothing there and say what you saw.",
    )
    notes: str = Field(
        default="",
        description="What you played and edited, and the claims no call can show with the reason "
        "for each. On `blocked`, the output that stopped you.",
    )
    findings: list[QaFinding] = Field(
        default=[],
        description="On `findings`, one entry per claim of the story the app does not meet: the "
        "claim in the story's words, the call, and the answer the app gave. Empty otherwise.",
    )
    calls: list[ServiceCalls] = Field(
        default=[],
        description="The calls you played, per covered service. The workflow selects what it plays "
        "from the story's diff, so this list is informative only.",
    )
    unreached: list[str] = Field(
        default=[],
        description="The story's claims you could not state in the book, one per entry, in the "
        "story's words, for example `no request reaches the report service`. A claim you stated "
        "and played is not listed. Empty when the book states every claim.",
    )


class BookPaths(CoderResult):
    """`changed_book_paths`: the uncommitted paths under the covered services' book folders."""

    paths: list[str] = []


class CoveredServices(CoderResult):
    """`covered_services`: the story's services that have an executable book."""

    services: list[str] = []


class BookPlay(CoderResult):
    """One run of the book tool: its exit code and the tail of its output."""

    exit_code: int = 0
    output: str = ""


class BookScope(CoderResult):
    """`book_scope`: whether a play of one service's book is the whole book, and the changed paths that decided it."""

    whole: bool = False
    shared: list[str] = []
    changed: int = 0


class BookQaRecord(CoderResult):
    """`book-qa.json`: the calls a passed check played, the findings it stood on and the claims the book could not state, so a later visit replays them."""

    services: list[ServiceCalls] = []
    findings: list[QaFinding] = []
    unreached: list[str] = []


class BookPlan(CoderResult):
    """`book_plan`: what `ostler book affected` selects to play for one service, merged over its modules."""

    service: str = ""
    plan: Literal["none", "empty", "partial", "whole"] = "none"
    only: list[str] = []
    by_journey: list[str] = []
    whole: bool = False
    reason: str = ""
    uncovered: list[str] = []
    changed: int = 0
    not_judged: int = 0
    exit_code: int = 0
    output: str = ""


class StoryBase(CoderResult):
    """`story_base_of`: the commit the story's own work started from, or empty when none is found."""

    base: str = ""


class UnreachedClaims(CoderResult):
    """`write_unreached_claims`: the claims `qa-unreached.json` now holds for the scenario seat."""

    claims: list[str] = []


__all__ = ["BookPaths", "BookPlan", "BookPlay", "BookQaOwnerResult", "BookQaRecord", "BookScope", "CoveredServices", "ServiceCalls", "StoryBase", "UnreachedClaims"]
