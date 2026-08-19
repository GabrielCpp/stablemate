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

from ostler import markdown

#: Emphasis around a bullet's *value*. `Bullet.label` already strips it from the key, and
#: both bold spellings are in live plans — `- **Level:** QA-only` puts the closing `**` on
#: the value's side of the colon, so without this the level reads as `** QA-only` and
#: matches no level name.
_EMPHASIS = "*_` "

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


def _words(title: str) -> list[str]:
    """A heading's words, lowercased, with a leading `5.`-style number dropped.

    The planner numbers this section as often as not, and the number is not part of what
    the heading says.
    """
    words = title.strip().lower().split()
    if words and words[0].rstrip(".").isdigit():
        words = words[1:]
    return words


def _is_scenarios_heading(title: str) -> bool:
    """Whether a heading opens the plan's scenario list — `## 5. Test Scenarios`."""
    return _words(title)[:2] == ["test", "scenarios"]


def _is_scenario_heading(title: str) -> bool:
    """Whether a heading opens one scenario — `### Scenario 3: Manual fallback`."""
    return _words(title)[:1] == ["scenario"]


def _scenario_sections(doc: markdown.MarkdownDoc) -> list[markdown.Section]:
    """The sections that are scenarios of the plan's Test Scenarios list, in source order.

    Scenario headings are written both a level below the list's own heading and level with
    it — `## 5. Test Scenarios` with `### Scenario 1: …` beneath, and `### Test Scenarios`
    with `### Scenario 1: …` beside. Nesting tells those apart and source order does not, so
    the walk takes both: anything titled `Scenario …` after the list's heading, plus any
    other heading still *inside* the list's span (a `#### Notes` under one scenario ends
    nothing). The first heading that is neither is where the list stops.
    """
    ordered = sorted(doc.walk_sections(), key=lambda section: section.line_start)
    for index, section in enumerate(ordered):
        if section.level and _is_scenarios_heading(section.title):
            break
    else:
        return []
    found: list[markdown.Section] = []
    for other in ordered[index + 1 :]:
        if _is_scenario_heading(other.title):
            found.append(other)
        elif other.line_start >= section.line_end:
            break
    return found


def _field(section: markdown.Section, label: str) -> str:
    """The value of this scenario's `- **Level**: …` bullet, or `""` when it has none."""
    bullet = section.labelled(label)
    return bullet.value.strip(_EMPHASIS).strip() if bullet else ""


def parse_scenarios(text: str) -> list[Scenario]:
    """Every scenario the plan's Test Scenarios section declares, with AC and level.

    A scenario is recognised by its heading, so a section written as prose yields
    nothing, which is the same answer as a plan with no such section at all. A heading
    that names no scenario after its colon — `### Scenario 3` — is skipped for the same
    reason: there is nothing for the QA lane to name in its plan.
    """
    doc = markdown.split(text)
    found: list[Scenario] = []
    for section in _scenario_sections(doc):
        title = section.title.partition(":")[2].strip()
        if title:
            found.append(Scenario(title, _field(section, "ac"), _field(section, "level")))
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
