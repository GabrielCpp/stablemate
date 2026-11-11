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
        "gives them. The run plays exactly these, so a call you leave out is never judged.",
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
        description="The calls you played, per covered service. Name at least one call for every "
        "covered service.",
    )
    unreached: list[str] = Field(
        default=[],
        description="The story's claims you could not state in the book, one per entry, in the "
        "story's words, for example `no request reaches the report service`. A claim you stated "
        "and played is not listed. Empty when the book states every claim.",
    )


class CoveredServices(CoderResult):
    """`covered_services`: the story's services that have an executable book."""

    services: list[str] = []


class BookPlay(CoderResult):
    """One run of the book tool: its exit code and the tail of its output."""

    exit_code: int = 0
    output: str = ""


class BookQaRecord(CoderResult):
    """`book-qa.json`: the calls a passed check played, the findings it stood on and the claims the book could not state, so a later visit replays them."""

    services: list[ServiceCalls] = []
    findings: list[QaFinding] = []
    unreached: list[str] = []


class BookDeferral(CoderResult):
    """`defer_book_judged`: how many obligations each recorded service's book took off the scenario lane."""

    marked: dict[str, int] = {}

__all__ = ["BookDeferral", "BookPlay", "BookQaOwnerResult", "BookQaRecord", "CoveredServices", "ServiceCalls"]
