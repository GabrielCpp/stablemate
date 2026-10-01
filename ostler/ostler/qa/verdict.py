"""The verdict each claim ends a run with, and the one it keeps when several checks judge it."""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from enum import StrEnum


class Verdict(StrEnum):
    """How one claim ended a run: its checks held, one of them did not, its scenario never reached them, or a capability it needs is absent from the stack.

    A gapped claim outweighs every other verdict, because a claim whose capability is absent is never failed.
    """

    PASS = "pass"
    FAIL = "fail"
    UNREACHED = "unreached"
    GAPPED = "gapped"


_WEIGHT = {Verdict.PASS: 0, Verdict.UNREACHED: 1, Verdict.FAIL: 2, Verdict.GAPPED: 3}


def judge(verdicts: dict[str, Verdict], claims: Iterable[str], verdict: Verdict) -> None:
    """Record *verdict* for each of *claims*, keeping a claim's worse verdict when it already has one."""
    for claim in claims:
        held = verdicts.get(claim)
        if held is None or _WEIGHT[verdict] > _WEIGHT[held]:
            verdicts[claim] = verdict


def merged(per_scenario: Iterable[Mapping[str, Verdict]]) -> dict[str, Verdict]:
    """Each claim's worst verdict across the scenarios that judged it, claims in order."""
    verdicts: dict[str, Verdict] = {}
    for scenario in per_scenario:
        for claim, verdict in scenario.items():
            judge(verdicts, (claim,), verdict)
    return dict(sorted(verdicts.items()))
