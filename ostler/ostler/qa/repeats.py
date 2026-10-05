"""Stop a run once one failure observation repeats across many scenarios and pages."""
from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from ostler.qa.drivers import ScenarioResult

MIN_PAGES = 3
OBSERVATION_CHARS = 300
PAGES_NAMED = 10
_PAGE = re.compile(r"^okf:(?P<page>[^#:]+\.md)")
_DIGITS = re.compile(r"\d+")
_SPACE = re.compile(r"\s+")


def observation(result: ScenarioResult) -> str:
    """What a failed scenario observed: the last line of its message, or its first failed check's actual value, with numbers blanked."""
    lines = [line.strip() for line in result.message.splitlines() if line.strip()]
    seen = lines[-1] if lines else next((check.actual for check in result.failed_checks if check.actual), "")
    return _SPACE.sub(" ", _DIGITS.sub("N", seen)).strip()[:OBSERVATION_CHARS]


def pages(covers: Iterable[object]) -> frozenset[str]:
    """The book pages a scenario's covered obligations live on."""
    return frozenset(match["page"] for claim in covers if (match := _PAGE.match(str(claim))))


@dataclass(slots=True)
class RepeatWatch:
    """The failure observations a run has seen so far, and the scenarios and pages each one spans."""

    threshold: int
    scenarios: dict[str, list[str]] = field(default_factory=dict)
    pages: dict[str, set[str]] = field(default_factory=dict)

    def observe(self, scenario_id: str, covers: Iterable[object], result: ScenarioResult) -> str:
        """Record one scenario's result, and say why the run should stop when its observation has repeated enough."""
        if self.threshold <= 0 or result.status == "passed":
            return ""
        if result.failed_checks and all(check.gap for check in result.failed_checks):
            return ""
        seen = observation(result)
        if not seen:
            return ""
        self.scenarios.setdefault(seen, []).append(scenario_id)
        self.pages.setdefault(seen, set()).update(pages(covers))
        failed, spanned = self.scenarios[seen], sorted(self.pages[seen])
        if len(failed) < self.threshold or len(spanned) < MIN_PAGES:
            return ""
        named = ", ".join(spanned[:PAGES_NAMED]) + (f" and {len(spanned) - PAGES_NAMED} more" if len(spanned) > PAGES_NAMED else "")
        return (f"the run stopped after {len(failed)} scenarios on {len(spanned)} pages failed on one observation, "
                f"so one cause outside any single page is likely: {seen} (pages: {named}). "
                f"Fix that cause first. The scenarios after {scenario_id} did not run")
