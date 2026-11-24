"""The History table and its totals judge an ended run against the median of its workflow."""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from ostler.book import Action, Actor, Transaction

from ..fixtures import Judged
from ..model.state import Dashboard

FLOOR = 5
ITEMS = 2
PEER_VISIT = 60.0
ENDINGS = {"gave-up": "gave up"}


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


@dataclass(frozen=True)
class TileCell:
    """What the Work items tile of the opened run says."""

    text: str

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class NodeCells:
    """What the By node table says of the comparison: its heading, an agent node's cell and a step node's cell."""

    heading: str
    agent: str
    step: str

    def __str__(self) -> str:
        return f"{self.heading} | agent node {self.agent} | step node {self.step}"


def each(value: float) -> str:
    return f"${round(value):,}" if value >= 10 else f"${value:.2f}"


def signed(percent: float) -> str:
    return ("−" if percent < 0 else "+") + f"{abs(round(percent))}%"


def plural(count: int, one: str, many: str) -> str:
    return f"{count} {one if count == 1 else many}"


def comparable(judged: Judged) -> bool:
    return judged.ending == "success" and not judged.estimate and judged.priced and judged.items > 0


def run_cell(judged: Judged) -> str:
    if judged.items == 0 or not (judged.priced or judged.estimate):
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
        return f"{each(statistics.median(pool))} {who}, {plural(len(pool), 'comparable run', 'comparable runs')}"
    only = f"only {plural(len(pool), 'comparable run', 'comparable runs')}" if pool else "no comparable run yet"
    return f"— {who}: {only}, and it takes {FLOOR}"


def not_compared(ending: str) -> str:
    if ending == "none":
        return "no ending recorded"
    if ending == "success":
        return "an estimate has no median"
    return f"the run {ENDINGS.get(ending, ending)}"


def tile_cell(judged: Judged) -> str:
    count = f"{judged.items} of {ITEMS}"
    if judged.items == 0:
        return f"{count} no item finished, so no cost per item"
    if judged.estimate:
        return f"{count} est {each(judged.each)} per item, not compared: {not_compared(judged.ending)}"
    if not judged.priced:
        return f"{count} no cost per item without a price"
    if judged.ending != "success":
        return f"{count} {each(judged.each)} per item, not compared: {not_compared(judged.ending)}"
    others = len(judged.peers)
    if others < FLOOR:
        kind = f"other comparable {judged.workflow} run"
        who = f"only {plural(others, kind, kind + 's')}" if others else f"no {kind} yet"
        return f"{count} {each(judged.each)} per item, no comparison: {who}, and it takes {FLOOR}"
    median = statistics.median(judged.peers)
    return f"{count} {each(judged.each)} per item {signed((judged.each - median) / median * 100)} vs median of {others} runs"


def node_cells(judged: Judged) -> NodeCells:
    others = len(judged.peers)
    if not comparable(judged):
        return NodeCells("vs median", "—", "—")
    if others < FLOOR:
        return NodeCells(f"vs median: {plural(others, 'run', 'runs')}, under five", "—", "—")
    return NodeCells(f"vs median of {others}", signed((judged.visit - PEER_VISIT) / PEER_VISIT * 100), "—")


class JudgeRun(Action[Judged, Dashboard]):
    accept = Judged

    @staticmethod
    def reduce(a: Judged, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction(says=(EachCell(run_cell(a)), MedianCell(totals_cell(a))))


class JudgeOpenedRun(Action[Judged, Dashboard]):
    accept = Judged

    @staticmethod
    def reduce(a: Judged, s: Dashboard, by: Actor | None) -> Transaction:
        return Transaction(says=(TileCell(tile_cell(a)), node_cells(a)))
