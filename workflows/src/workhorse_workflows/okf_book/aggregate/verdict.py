"""The judge's verdict on a job's pages: one finding for each numbered contract claim, and the problems no claim covers.

The code, not the judge, decides the pass. A claim the judge leaves unaccounted is a claim no page states.
A node an earlier round cleared stays cleared while its text is unchanged, so a later round cannot fault it again.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from ostler.checks import Refusal, parse_check
from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.attempts import ClearedNode
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
    expected: str = ""


class NodeProblem(BaseModel):
    """A problem no claim covers, on the node it is on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node: str
    problem: str
    expected: str = ""


class GrammarGap(BaseModel):
    """A check the judge expected that the check grammar cannot state."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    node: str
    problem: str
    expected: str
    refusal: str


GRAMMAR_GAPS_NAME = "grammar-gaps.jsonl"


class Verdict(BaseModel):
    """A later turn's judgement of the pages another turn wrote."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    claims: tuple[ClaimFinding, ...] = ()
    problems: tuple[NodeProblem, ...] = ()


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


def still_cleared(cleared: tuple[ClearedNode, ...], digests: Mapping[str, str]) -> tuple[ClearedNode, ...]:
    """Each cleared node whose text is still the text it was cleared at."""
    return tuple(entry for entry in cleared if digests.get(entry.node) == entry.digest)


def verdict_problems(verdict: Verdict, claims: tuple[str, ...], still_cleared_nodes: tuple[ClearedNode, ...]) -> tuple[str, ...]:
    """The problems the verdict charges the job: each claim no node states, each finding's problem, then each problem no claim covers.

    A problem on a node still cleared is dropped, and a claim such a node states is stated.
    """
    cleared_by_node = {entry.node: entry for entry in still_cleared_nodes}
    stated_by_cleared = {claim for entry in cleared_by_node.values() for claim in entry.claims}
    stated = {finding.claim for finding in verdict.claims if finding.node}
    unstated = tuple(
        f"Claim {number}, {text}, is stated on no page. State it on the node that owns that code, "
        "as a claim whose `verify:` goes red when the product breaks it."
        for number, text in enumerate(claims, start=1)
        if number not in stated and text not in stated_by_cleared
    )
    flawed = tuple(
        f"{finding.node or f'Claim {finding.claim}'}: {finding.problem}{_expected_hint(finding.expected)}"
        for finding in verdict.claims
        if finding.problem and finding.node not in cleared_by_node
    )
    uncovered = tuple(
        f"{found.node}: {found.problem}{_expected_hint(found.expected)}"
        for found in verdict.problems
        if found.node not in cleared_by_node
    )
    return (*unstated, *flawed, *uncovered)


def _expected_hint(expected: str) -> str:
    """The check the judge expected, as the writer is told it, when the check grammar can state it."""
    parsed = parse_check(expected) if expected else None
    if parsed is None or isinstance(parsed, Refusal):
        return ""
    return f" The check that reads it: `verify: {parsed.text()}`."


def grammar_gaps(verdict: Verdict) -> tuple[GrammarGap, ...]:
    """Each check the judge expected on a problem that the check grammar refuses, with the refusal."""
    found = [
        *((finding.node or f"Claim {finding.claim}", finding.problem, finding.expected) for finding in verdict.claims if finding.problem),
        *((problem.node, problem.problem, problem.expected) for problem in verdict.problems),
    ]
    gaps: list[GrammarGap] = []
    for node, problem, expected in found:
        parsed = parse_check(expected) if expected else None
        if isinstance(parsed, Refusal):
            gaps.append(GrammarGap(node=node, problem=problem, expected=expected, refusal=parsed.message))
    return tuple(gaps)


def record_grammar_gaps(run_dir: Path, gaps: tuple[GrammarGap, ...]) -> None:
    """Append each gap to the run's grammar-gap record that it does not hold yet, so a retried append adds nothing."""
    record = run_dir / GRAMMAR_GAPS_NAME
    held = set(record.read_text(encoding="utf-8").splitlines()) if record.is_file() else set[str]()
    lines = list(dict.fromkeys(line for line in (gap.model_dump_json() for gap in gaps) if line not in held))
    if not lines:
        return
    run_dir.mkdir(parents=True, exist_ok=True)
    with record.open("a", encoding="utf-8") as out:
        _ = out.write("".join(line + "\n" for line in lines))


def _claims_stated_on(verdict: Verdict, claims: tuple[str, ...]) -> dict[str, set[str]]:
    """Each node the verdict found stating a claim with no problem, and the claims it states."""
    stated_on: dict[str, set[str]] = {}
    for finding in verdict.claims:
        if finding.node and not finding.problem and 1 <= finding.claim <= len(claims):
            stated_on.setdefault(finding.node, set()).add(claims[finding.claim - 1])
    return stated_on


def _judged_nodes_cleared(verdict: Verdict, judged: Iterable[str], cleared_by_node: Mapping[str, ClearedNode]) -> tuple[str, ...]:
    """Each judged node still cleared, and each the verdict raised nothing against."""
    faulted = {finding.node for finding in verdict.claims if finding.problem} | {found.node for found in verdict.problems}
    return tuple(node for node in judged if node in cleared_by_node or node not in faulted)


def cleared_after(
    verdict: Verdict, claims: tuple[str, ...], judged_node_digests: Mapping[str, str], still_cleared_nodes: tuple[ClearedNode, ...],
) -> tuple[ClearedNode, ...]:
    """The nodes cleared once this verdict is in: those still cleared, judged or not, and each judged node it raised nothing against."""
    cleared_by_node = {entry.node: entry for entry in still_cleared_nodes}
    stated_on = _claims_stated_on(verdict, claims)
    cleared_now: dict[str, ClearedNode] = {}
    for node in _judged_nodes_cleared(verdict, judged_node_digests, cleared_by_node):
        claims_cleared_before = cleared_by_node[node].claims if node in cleared_by_node else ()
        stated = tuple(sorted(stated_on.get(node, set()) | set(claims_cleared_before)))
        cleared_now[node] = ClearedNode(node=node, digest=judged_node_digests[node], claims=stated)
    return tuple({**cleared_by_node, **cleared_now}.values())
