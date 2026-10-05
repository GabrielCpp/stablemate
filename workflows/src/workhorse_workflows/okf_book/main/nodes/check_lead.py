"""What the lead of a page check is shown, what its verdict names, and which problems it holds back from the page repair.

A check groups its problems by the code of the rule that raised them. The lead names the side of
each group, or splits one group by its nodes. A problem in a group the lead named another side's is
held: no page repair is sent it, and it is a blocker on that side.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ostler.qa.attribution import Cause

from workhorse_workflows.okf_book.main.nodes.gate import rerun_command
from workhorse_workflows.okf_book.main.nodes.lead_findings import CAUSE_BY_OTHER_SIDE, LEAD_SIDES, LeadFinding, LeadVerdict, service_findings
from workhorse_workflows.okf_book.shared.blockers import Blocker, Phase, Side, forget_blockers, read_blockers, record_blocker
from workhorse_workflows.okf_book.shared.page_check import PageProblem, tool_blockers

PROBLEMS_NAME = "check-problems.txt"
SAMPLES_SHOWN = 3
NODES_SHOWN = 12


@dataclass(frozen=True, slots=True)
class CheckGroup:
    """The problems of one check that one rule raised."""

    code: str
    problems: tuple[PageProblem, ...]

    @property
    def pages(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(problem.page for problem in self.problems))

    @property
    def nodes(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(problem.node or problem.page for problem in self.problems))


def check_groups(problems: Iterable[PageProblem]) -> tuple[CheckGroup, ...]:
    """The problems grouped by the code of their rule, the largest group first."""
    by_code: dict[str, list[PageProblem]] = {}
    for problem in problems:
        by_code.setdefault(problem.code, []).append(problem)
    return tuple(CheckGroup(code, tuple(found)) for code, found in sorted(by_code.items(), key=lambda item: (-len(item[1]), item[0])))


def _names(problem: PageProblem, nodes: Iterable[str]) -> bool:
    return any(named in (problem.node, problem.page) for named in nodes)


def check_findings(service: str, lap: int, problems: Iterable[PageProblem], verdict: LeadVerdict) -> tuple[LeadFinding, ...]:
    """Each verdict that judges at least one problem of a group of the check, as a finding. A verdict that names nodes judges the group's problems on them, and the last verdict that names none judges the rest. A verdict on a number the check has no group for is dropped."""
    groups = check_groups(problems)
    findings: list[LeadFinding] = []
    for number, group in enumerate(groups, start=1):
        judged = [verdict_ for verdict_ in verdict.findings if verdict_.group == number]
        split = [verdict_ for verdict_ in judged if verdict_.nodes]
        rest = next((verdict_ for verdict_ in reversed(judged) if not verdict_.nodes), None)
        claimed: set[PageProblem] = set()
        for verdict_ in (*split, *(() if rest is None else (rest,))):
            covered = tuple(problem for problem in group.problems if problem not in claimed and (not verdict_.nodes or _names(problem, verdict_.nodes)))
            claimed.update(covered)
            if not covered:
                continue
            findings.append(LeadFinding(
                service=service, lap=lap, signature=group.code, count=len(covered), side=verdict_.side, evidence=verdict_.evidence,
                instruction=verdict_.instruction if verdict_.side is Side.BOOK else "",
                pages=tuple(dict.fromkeys(problem.page for problem in covered)), measured="check", nodes=verdict_.nodes,
            ))
    return tuple(findings)


def latest_check_findings(findings: Iterable[LeadFinding], service: str) -> tuple[LeadFinding, ...]:
    """The findings of the last lead that read *service*'s page check."""
    checked = service_findings(findings, service, measured="check")
    last = max((finding.lap for finding in checked), default=0)
    return tuple(finding for finding in checked if finding.lap == last)


def next_check_lap(findings: Iterable[LeadFinding], service: str) -> int:
    return 1 + max((finding.lap for finding in service_findings(findings, service, measured="check")), default=0)


def judging(problem: PageProblem, findings: Iterable[LeadFinding]) -> LeadFinding | None:
    """The finding that judges *problem*: the one of its code that names its node, else the one of its code that names none."""
    same_code = [finding for finding in findings if finding.signature == problem.code]
    return next((finding for finding in same_code if finding.nodes and _names(problem, finding.nodes)),
                next((finding for finding in same_code if not finding.nodes), None))


def held(problems: Iterable[PageProblem], findings: Iterable[LeadFinding]) -> tuple[tuple[PageProblem, LeadFinding], ...]:
    """Each problem a finding names another side's than the book's, with that finding."""
    kept = tuple(findings)
    pairs = ((problem, judging(problem, kept)) for problem in problems)
    return tuple((problem, finding) for problem, finding in pairs if finding is not None and finding.side is not Side.BOOK)


def unheld(problems: Iterable[PageProblem], findings: Iterable[LeadFinding]) -> tuple[PageProblem, ...]:
    """The problems no finding holds back, in their order."""
    found = tuple(problems)
    keys = {problem.held_key for problem, _finding in held(found, findings)}
    return tuple(problem for problem in found if problem.held_key not in keys)


def with_check_instructions(problems: Iterable[PageProblem], findings: Iterable[LeadFinding]) -> tuple[PageProblem, ...]:
    """*problems* with what the lead said to do first on each page of a group it named the book's, ahead of the page's problems."""
    found = tuple(problems)
    told: dict[str, list[PageProblem]] = {}
    for finding in findings:
        if finding.side is not Side.BOOK or not finding.instruction:
            continue
        for page in dict.fromkeys(problem.page for problem in found if judging(problem, (finding,)) is finding):
            told.setdefault(page, []).append(
                PageProblem(page, f"the lead read the whole check, and says of {finding.signature}: {finding.instruction}", code="lead")
            )
    return (*(note for notes in told.values() for note in notes), *found)


def write_check_problems(folder: Path, problems: Iterable[PageProblem]) -> Path:
    """Write every problem of the check, one per line, where the lead turn reads it."""
    path = folder / PROBLEMS_NAME
    _ = path.write_text("".join(f"{problem.code}\t{problem.text}\n" for problem in problems), encoding="utf-8")
    return path


def check_lead_template_args(service: str, problems: Iterable[PageProblem], earlier: Iterable[LeadFinding], kept_problems: Path) -> dict[str, object]:
    """What the lead of a check is shown: each group with its count, some of its problems, its pages and nodes, where every problem is kept, and what earlier leads of the check named."""
    groups = [
        {"number": number, "code": group.code, "count": len(group.problems),
         "samples": [problem.text for problem in group.problems[:SAMPLES_SHOWN]],
         "pages": list(group.pages), "nodes": list(group.nodes[:NODES_SHOWN]), "nodes_left": max(0, len(group.nodes) - NODES_SHOWN)}
        for number, group in enumerate(check_groups(problems), start=1)
    ]
    return {
        "service": service,
        "groups": groups,
        "problems": str(kept_problems),
        "sides": sorted(LEAD_SIDES),
        "earlier": [finding.model_dump(mode="json") for finding in earlier],
    }


def held_reasons(pairs: Iterable[tuple[PageProblem, LeadFinding]]) -> Mapping[LeadFinding, tuple[PageProblem, ...]]:
    """The held problems under the finding that holds them."""
    by_finding: dict[LeadFinding, list[PageProblem]] = {}
    for problem, finding in pairs:
        by_finding.setdefault(finding, []).append(problem)
    return {finding: tuple(found) for finding, found in by_finding.items()}


def record_check(records_dir: Path, root: Path, service: str, problems: tuple[PageProblem, ...], findings: tuple[LeadFinding, ...] = ()) -> int:
    """Make each problem of a check a blocker on its page, in place of the ones the last check left, and each rule the lead named another side's one blocker on that side. Returns how many problems the last check left the book."""
    before = sum(1 for blocker in read_blockers(records_dir)
                 if blocker.phase is Phase.WRITE and blocker.side is Side.BOOK and blocker.service == service)
    for side in (Side.BOOK, *CAUSE_BY_OTHER_SIDE):
        forget_blockers(records_dir, Phase.WRITE, side, service)
    for tool in tool_blockers(root, service):
        _ = record_blocker(records_dir, tool)
    for problem in unheld(problems, findings):
        blocker = Blocker(subject=f"{service}: {problem.text}", service=service, phase=Phase.WRITE, side=Side.BOOK, reason=problem.text,
                          cause=Cause.BOOK.value, pages=(problem.page,),
                          rerun=rerun_command(records_dir, service, Phase.WRITE, (problem.page,)))
        _ = record_blocker(records_dir, blocker)
    for finding, found in held_reasons(held(problems, findings)).items():
        pages = tuple(dict.fromkeys(problem.page for problem in found))
        on = f" on {', '.join(finding.nodes)}" if finding.nodes else ""
        reason = "\n".join((*(problem.text for problem in found), f"the lead read the whole check: {finding.evidence}"))
        blocker = Blocker(subject=f"{service}: {finding.signature}{on}", service=service, phase=Phase.WRITE, side=finding.side, reason=reason,
                          cause=CAUSE_BY_OTHER_SIDE[finding.side].value, pages=pages,
                          rerun=rerun_command(records_dir, service, Phase.WRITE, pages))
        _ = record_blocker(records_dir, blocker)
    return before
