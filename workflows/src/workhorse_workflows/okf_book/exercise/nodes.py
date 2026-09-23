"""What phase 3's turns read and return: the scenarios that fit a turn, the pages a failure covers, and each turn's reply."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from workhorse_workflows.okf_book.shared.budget import Packed, estimated_tokens, file_tokens, pack_told
from workhorse_workflows.okf_book.shared.page_check import obligation_page
from workhorse_workflows.okf_book.shared.scenarios import Scenario, plan_scenarios, spec_dir


class FlowPick(BaseModel):
    """The scenarios a turn chose to run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ids: tuple[str, ...]


class Judgement(BaseModel):
    """Which side a failed scenario is charged to, and why, as an agent holding only the book reads it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    side: Literal["app", "book"]
    reason: str


def scenario_tokens(scenarios: tuple[Scenario, ...]) -> int:
    return estimated_tokens(sum(len(s.model_dump_json()) for s in scenarios))


def covers_of(root: Path, records_dir: Path, scenario: str) -> tuple[str, ...]:
    scenarios, _problems = plan_scenarios(root, spec_dir(records_dir))
    return next((s.covers for s in scenarios if s.id == scenario), ())


def covered_pages(root: Path, covers: tuple[str, ...], budget: int) -> Packed:
    named = dict.fromkeys(obligation_page(obligation) for obligation in covers)
    return pack_told(file_tokens(root, (page for page in named if page and (root / page).is_file())), budget)


@dataclass(frozen=True, slots=True)
class ScenarioSplit:
    """The scenarios one turn reads within budget, and the ids of the rest, which run without being picked."""

    read: tuple[Scenario, ...]
    unread_ids: tuple[str, ...]


def split_by_budget(scenarios: tuple[Scenario, ...], budget: int) -> ScenarioSplit:
    """The scenarios in order while they fit the budget, and every one after the first that does not."""
    read: list[Scenario] = []
    spent = 0
    for scenario in scenarios:
        spent += scenario_tokens((scenario,))
        if spent > budget:
            break
        read.append(scenario)
    return ScenarioSplit(tuple(read), tuple(s.id for s in scenarios[len(read):]))
