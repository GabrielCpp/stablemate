"""The History table and its totals judge an ended run against the median of its workflow."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from ostler.book import Action, Actor, Transaction

from ..fixtures import Judged
from ..model.state import Dashboard

FLOOR = 5


@dataclass(frozen=True)
class EachCell:
    """What the run's cell under $/item vs median says."""

    text: str

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class MedianCell:
    """What the totals say of the median once the workflow is chosen."""

    text: str

    def __str__(self) -> str:
        return self.text


def each(value: float) -> str:
    return f"${round(value):,}" if value >= 10 else f"${value:.2f}"


def signed(percent: float) -> str:
    return ("−" if percent < 0 else "+") + f"{abs(round(percent))}%"


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def comparable(judged: Judged) -> bool:
    return judged.ending == "success" and not judged.estimate and judged.items > 0


def run_cell(judged: Judged) -> str:
    if judged.items == 0:
        return "—"
    if judged.estimate:
        return f"est {each(judged.each)}"
    if not comparable(judged) or len(judged.peers) < FLOOR:
        return each(judged.each)
    median = statistics.median(judged.peers)
    return f"{each(judged.each)} {signed((judged.each - median) / median * 100)}"


def totals_cell(judged: Judged) -> str:
    pool = (*judged.peers, judged.each) if comparable(judged) else judged.peers
    who = f"median per {judged.workflow} item"
    if len(pool) >= FLOOR:
        return f"${statistics.median(pool):.2f} {who}, {plural(len(pool), 'comparable run', 'comparable runs')}"
    only = f"only {plural(len(pool), 'comparable run', 'comparable runs')}" if pool else "no comparable run yet"
    return f"— {who}: {only}, and it takes {FLOOR}"


class JudgeRun(Action[Judged, Dashboard]):
    accept = Judged

    @staticmethod
    def reduce(a: Judged, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction(says=(EachCell(run_cell(a)), MedianCell(totals_cell(a))))
