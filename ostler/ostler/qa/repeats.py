"""Stop a run once one failure observation repeats across many scenarios and pages."""
from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ostler.qa.drivers import FailedCheck, ScenarioResult

MIN_PAGES = 3
OBSERVATION_CHARS = 300
PAGES_NAMED = 10
_PAGE = re.compile(r"^okf:(?P<page>[^#:]+\.md)")
_DIGITS = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")
_ABSENT = re.compile(r'"present":\s*false|^missing: ')


def _observed(check: FailedCheck) -> str:
    return f"{check.label}: {check.actual}" if _ABSENT.search(check.actual) else check.actual


def observation(result: ScenarioResult, scenario_id: str = "") -> str:
    """What a failed scenario observed: the last problem on the last line of its message, or its first failed check's actual value, with its own id and numbers blanked.

    An element a check found absent is named with that check, since a different element missing on each page is no one cause.
    """
    lines = [line.strip() for line in result.message.splitlines() if line.strip()]
    seen = lines[-1].rsplit("; ", 1)[-1] if lines else next((_observed(check) for check in result.failed_checks if check.actual), "")
    if scenario_id:
        seen = seen.replace(scenario_id, "<scenario>")
    return _SPACE.sub(" ", _DIGITS.sub("N", seen)).strip()[:OBSERVATION_CHARS]


def pages(covers: Iterable[object]) -> frozenset[str]:
    """The book pages a scenario's covered obligations live on."""
    return frozenset(match["page"] for claim in covers if (match := _PAGE.match(str(claim))))


@dataclass(slots=True)
class RepeatWatch:
    """The failure observations a run has seen so far, the scenarios and pages each one spans, and the one that stopped the run."""

    threshold: int
    min_pages: int = MIN_PAGES
    scenarios: dict[str, list[str]] = field(default_factory=dict)
    pages: dict[str, set[str]] = field(default_factory=dict)
    stopped_on: str = ""

    def observe(self, scenario_id: str, covers: Iterable[object], result: ScenarioResult) -> str:
        """Record one scenario's result, and say why the run should stop when its observation has repeated enough."""
        if self.threshold <= 0 or result.status == "passed":
            return ""
        if result.failed_checks and all(check.gap for check in result.failed_checks):
            return ""
        seen = observation(result, scenario_id)
        if not seen:
            return ""
        self.scenarios.setdefault(seen, []).append(scenario_id)
        self.pages.setdefault(seen, set()).update(pages(covers))
        failed, spanned = self.scenarios[seen], sorted(self.pages[seen])
        if len(failed) < self.threshold or len(spanned) < self.min_pages:
            return ""
        self.stopped_on = seen
        named = ", ".join(spanned[:PAGES_NAMED]) + (f" and {len(spanned) - PAGES_NAMED} more" if len(spanned) > PAGES_NAMED else "")
        likely = ", so one cause outside any single page is likely" if len(spanned) >= MIN_PAGES else ""
        return (f"the run stopped after {len(failed)} scenarios on {len(spanned)} pages failed on one observation{likely}: "
                f"{seen} (pages: {named}). Fix that cause first. The scenarios after {scenario_id} did not run")


def watch_for(threshold: int, scenarios: Iterable[Mapping[str, object]], *, scoped: bool = False) -> RepeatWatch:
    """The watch over a run of *scenarios*, which asks a repeat to span as many pages as the run holds, up to MIN_PAGES.

    A *scoped* run names its scenarios for the pages one writer is fixing, so a repeat on any one of them stops it.
    """
    if scoped:
        return RepeatWatch(threshold, 1)
    held = pages(claim for scenario in scenarios for claim in _claims(scenario.get("covers")))
    return RepeatWatch(threshold, min(MIN_PAGES, max(len(held), 1)))


def _claims(covers: object) -> list[object]:
    return list(covers) if isinstance(covers, list | tuple) else []
