"""The end review's verdicts, read against the story's criteria."""
from __future__ import annotations

from workhorse_workflows.coder.shared.schemas.book_qa import BookQaRecord, ReviewVerdict
from workhorse_workflows.coder.shared.schemas.qa import QaFinding

REVIEW_LAPS = 1


def by_criterion(verdicts: list[ReviewVerdict], count: int) -> dict[int, ReviewVerdict]:
    """The first verdict given each criterion numbered 1 to `count`. A number outside that range is dropped."""
    held: dict[int, ReviewVerdict] = {}
    for verdict in verdicts:
        if 1 <= verdict.criterion <= count:
            held.setdefault(verdict.criterion, verdict)
    return held


def missing_criteria(verdicts: list[ReviewVerdict], count: int) -> list[int]:
    """The criterion numbers with no verdict, in order."""
    held = by_criterion(verdicts, count)
    return [n for n in range(1, count + 1) if n not in held]


def missing_text(missing: list[int]) -> str:
    """Return the report the review's next turn reads."""
    return (
        f"The review gave no verdict for criterion {', '.join(map(str, missing))}. "
        "Give one verdict for each criterion of the list."
    )


def unmet_findings(verdicts: list[ReviewVerdict], criteria: list[str], story_path: str) -> list[QaFinding]:
    """One finding per `unmet` criterion, for the developer."""
    held = by_criterion(verdicts, len(criteria))
    return [
        QaFinding(
            id=f"review-criterion-{n}",
            target=verdict.target or story_path,
            issue=f"Acceptance criterion {n} is unmet: {criteria[n - 1]}. {verdict.evidence}".strip(),
            repair=verdict.repair or "Meet the criterion as the story states it.",
        )
        for n, verdict in sorted(held.items())
        if verdict.verdict == "unmet"
    ]


def unobserved(verdicts: list[ReviewVerdict], count: int) -> list[ReviewVerdict]:
    """The verdicts of `unobserved` kind, in criterion order."""
    held = by_criterion(verdicts, count)
    return [verdict for _, verdict in sorted(held.items()) if verdict.verdict == "unobserved"]


def owed_claims(record: BookQaRecord, criteria: list[str]) -> list[str]:
    """The claims the scenario seat owes: the ones the books could not state, then each criterion no play observed. A record with a finding owes none, because the story goes back to its developer."""
    if record.findings:
        return []
    return [*record.unreached, *(_unseen_claim(v, criteria) for v in record.unobserved)]


def _unseen_claim(verdict: ReviewVerdict, criteria: list[str]) -> str:
    n = verdict.criterion
    text = criteria[n - 1] if 1 <= n <= len(criteria) else f"criterion {n} of the story"
    why = f": {verdict.evidence}" if verdict.evidence else ""
    return f"{text} (acceptance criterion {n}, which no book play observed{why})"


__all__ = ["REVIEW_LAPS", "by_criterion", "missing_criteria", "missing_text", "owed_claims", "unmet_findings", "unobserved"]
