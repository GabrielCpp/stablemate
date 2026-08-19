"""The plan's `## 5. Test Scenarios` section, parsed for the QA lane's obligations.

`qa/flow.py` needs to know which of the plan's scenarios the dev lane decided not to write
an automated test for (`Level: QA-only` and its e2e/manual spellings) — a scenario excluded
from the suite and handed to nobody is not covered by anything in the run, so those become
the QA plan's `qa_only_scenarios` input.

This module used to have a second consumer, the dev lane's red gate, which decided whether
to run the tests-first split at all from the same parse. The split and the gate are gone —
see `dev/flow.py` — and with them the marker-escape machinery (`plan_escape`,
`declares_marker`, the literal `regression-only`/`qa-only` markers) that existed only to
drive that decision. What is left is the parse itself and the one predicate QA still reads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: The `## 5. Test Scenarios` heading, however the planner numbered or cased it.
_SECTION_HEADING = re.compile(r"^#{2,3}\s*(?:\d+\.\s*)?test scenarios\b", re.IGNORECASE)

#: Any heading at the same level or shallower ends the section.
_ANY_HEADING = re.compile(r"^#{1,3}\s")

#: One scenario inside the section: `### Scenario 3: Manual fallback covers gaps`.
_SCENARIO_HEADING = re.compile(r"^#{3,4}\s*scenario\b[^:\n]*:?\s*(?P<title>.*)$", re.IGNORECASE)

#: A `- **Level:** QA-only — reason` / `- **AC**: 2. …` bullet. Both bold spellings are in
#: live plans and they put the colon on opposite sides of the closing `**`, so the emphasis
#: is stripped on both sides of it — otherwise the level reads as `** QA-only` and matches
#: nothing.
_FIELD = re.compile(
    r"^\s*[-*]\s*\*{0,2}(?P<field>AC|Level)\*{0,2}\s*:\s*\*{0,2}\s*(?P<value>.*?)\s*\*{0,2}$",
    re.IGNORECASE,
)

#: The dash between a level's name and the planner's justification for it.
_LEVEL_REASON = re.compile(r"\s+[—–]\s*|\s+-\s+|\s*[(,]")

#: Levels that write no test in this run. `QA-only` is the planner's own label; the e2e
#: spellings are here because a plan that routes everything through a live browser has
#: left the tests turn nothing to write either, whatever it called that.
_NO_TEST_LEVELS = {"qa-only", "qa only", "e2e", "end-to-end", "manual"}


@dataclass(frozen=True)
class Scenario:
    """One entry of the plan's scenario list, reduced to what both lanes branch on."""

    title: str
    ac: str
    level: str

    @property
    def writes_no_test(self) -> bool:
        """Whether this scenario's level means no automated test is planned for it.

        The level is `QA-only — visual layout`: a name, then a dash, then the planner's
        justification. Only a *spaced* dash separates them, because the level names
        themselves contain hyphens (`QA-only`, `end-to-end`) and splitting on a bare one
        leaves `QA`, which matches nothing.
        """
        head = _LEVEL_REASON.split(self.level, maxsplit=1)[0]
        return head.strip().lower() in _NO_TEST_LEVELS


def _section(text: str) -> list[str]:
    """The lines of the plan's Test Scenarios section, or none when it has none."""
    lines = text.splitlines()
    for start, line in enumerate(lines):
        if _SECTION_HEADING.match(line):
            break
    else:
        return []
    body: list[str] = []
    for line in lines[start + 1 :]:
        if _ANY_HEADING.match(line) and not _SCENARIO_HEADING.match(line):
            break
        body.append(line)
    return body


def parse_scenarios(text: str) -> list[Scenario]:
    """Every scenario the plan's Test Scenarios section declares, with AC and level.

    A scenario is recognised by its heading, so a section written as prose yields
    nothing, which is the same answer as a plan with no such section at all.
    """
    found: list[Scenario] = []
    title, fields = "", {"ac": "", "level": ""}
    for line in _section(text):
        heading = _SCENARIO_HEADING.match(line)
        if heading:
            if title:
                found.append(Scenario(title, fields["ac"], fields["level"]))
            title, fields = heading.group("title").strip(), {"ac": "", "level": ""}
            continue
        field = _FIELD.match(line)
        if field and title:
            fields[field.group("field").lower()] = field.group("value").strip()
    if title:
        found.append(Scenario(title, fields["ac"], fields["level"]))
    return found


def _plan_texts(spec_abs: Path | None, plan_file: str) -> list[str]:
    """The layer's plan and the root plan, in that order, skipping what cannot be read."""
    if spec_abs is None:
        return []
    texts: list[str] = []
    for name in dict.fromkeys((plan_file, "plan.md")):
        if not name:
            continue
        try:
            texts.append((spec_abs / name).read_text(encoding="utf-8"))
        except OSError:
            continue
    return texts


def qa_only_scenarios(spec_abs: Path | None, plan_file: str) -> list[Scenario]:
    """The scenarios the dev plan marked as writing no test — the QA lane's obligations.

    Taken from the first plan that parses to any scenario at all, so a layer plan that
    carries the list is not silently merged with the root plan's copy of it.
    """
    for text in _plan_texts(spec_abs, plan_file):
        scenarios = parse_scenarios(text)
        if scenarios:
            return [scenario for scenario in scenarios if scenario.writes_no_test]
    return []


__all__ = [
    "Scenario",
    "parse_scenarios",
    "qa_only_scenarios",
]
