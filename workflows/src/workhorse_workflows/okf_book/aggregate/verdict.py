"""The judge's verdict on a job's pages: one finding for each numbered contract claim, and the problems no claim covers.

The code, not the judge, decides the pass. A claim the judge leaves unaccounted is a claim no page states.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.contracts import Contract


class NumberedClaim(BaseModel):
    """One contract claim, numbered across every contract the judge is handed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: int
    text: str
    symbol: str = ""


class NumberedContract(BaseModel):
    """A contract as the judge reads it: its promises and refusals as one numbered list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    file: str
    purpose: str
    claims: tuple[NumberedClaim, ...]


class ClaimFinding(BaseModel):
    """Where the judge found one claim stated, and what is wrong with it there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claim: int
    node: str = ""
    problem: str = ""


class Verdict(BaseModel):
    """A later turn's judgement of the pages another turn wrote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[ClaimFinding, ...] = ()
    problems: tuple[str, ...] = ()


def numbered_contracts(contracts: tuple[Contract, ...]) -> tuple[NumberedContract, ...]:
    """Number every promise and refusal across *contracts*, from 1."""
    numbered: list[NumberedContract] = []
    count = 0
    for contract in contracts:
        claims = tuple(
            NumberedClaim(id=count + offset, text=claim.text, symbol=claim.symbol)
            for offset, claim in enumerate(contract.claims, start=1)
        )
        count += len(claims)
        numbered.append(NumberedContract(file=contract.file, purpose=contract.purpose, claims=claims))
    return tuple(numbered)


def claim_texts(contracts: tuple[NumberedContract, ...]) -> tuple[str, ...]:
    """Each numbered claim as a problem names it, in number order."""
    return tuple(
        f"{claim.text} (`{contract.file}::{claim.symbol}`)" if claim.symbol else f"{claim.text} (`{contract.file}`)"
        for contract in contracts
        for claim in contract.claims
    )


def verdict_problems(verdict: Verdict, claims: tuple[str, ...]) -> tuple[str, ...]:
    """The problems the verdict charges the job: each claim no node states, each finding's problem, then the rest."""
    stated = {finding.claim for finding in verdict.claims if finding.node}
    unstated = tuple(
        f"Claim {number}, {text}, is stated on no page. State it on the node that owns that code, "
        "as a claim whose `verify:` goes red when the product breaks it."
        for number, text in enumerate(claims, start=1)
        if number not in stated
    )
    flawed = tuple(
        f"{finding.node or f'Claim {finding.claim}'}: {finding.problem}" for finding in verdict.claims if finding.problem
    )
    return (*unstated, *flawed, *verdict.problems)
