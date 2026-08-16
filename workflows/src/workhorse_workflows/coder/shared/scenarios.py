"""The plan's `## 5. Test Scenarios` section, parsed once for both lanes.

Two consumers need the same reading of this section and must not disagree about it:

* the **dev lane's red gate** (`red_gate.arm_red_gate`), which decides whether to run the
  tests-first split at all — a story whose every scenario is `Level: QA-only` has nothing
  the tests turn may legitimately write, so the split is unwinnable and the gate must
  stand aside rather than spend three high-power turns discovering that;
* the **QA lane's planner** (`qa/flow.py`), which has to receive those same scenarios as
  obligations, because a scenario excluded from the suite and handed to nobody is not
  covered by anything in the run.

It lives here, not inside `red_gate.py`, so the QA lane can have the parse without
importing the dev lane's gate to get it.

**Both triggers, deliberately.** The planner is told to write the marker down
(`plan-story.md`), *and* the escape is derived from the `**Level:**` lines when it does
not. Prompt-only is an instruction a real plan has already ignored once; derivation-only
leaves the plan document self-contradictory — a scenario list the tests turn is told to
exclude, with nothing at the top of the section saying so.

A section that is absent, or that parses to nothing, yields no escape. That direction is
deliberate: falling back to the TDD path costs a rework lap, while inventing the escape
silently disables the gate for a story that needed it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

#: The planner's literal escapes, matched case-insensitively anywhere in the plan.
REGRESSION_ONLY_MARKER = "test scenarios: regression-only"
QA_ONLY_MARKER = "test scenarios: qa-only"

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

    A scenario is recognised by its heading, so a section written as prose — the shape
    the regression-only escape produces — yields nothing, which is the same answer as a
    plan with no such section at all.
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


def _marker_escape(text: str) -> str:
    """Which literal escape the text carries, if any."""
    lowered = text.lower()
    if REGRESSION_ONLY_MARKER in lowered:
        return "regression_only"
    if QA_ONLY_MARKER in lowered:
        return "qa_only"
    return ""


def _derived_escape(text: str) -> str:
    """`qa_only` when the text parses to scenarios and every one writes no test."""
    scenarios = parse_scenarios(text)
    if scenarios and all(scenario.writes_no_test for scenario in scenarios):
        return "qa_only"
    return ""


def escape_in_text(text: str) -> str:
    """`plan_escape` for a plan already in hand — the packet lane's checkpointed snapshot.

    The packet lane reads its plan from the checkpoint rather than from disk, so that a
    plan edited mid-run cannot flip the route between packets. It needs the same verdict
    from the same rules, without the file lookup.
    """
    return _marker_escape(text) or _derived_escape(text)


def plan_escape(spec_abs: Path | None, plan_file: str) -> str:
    """`""`, `"regression_only"` or `"qa_only"` — which escape, if any, the plan declares.

    The literal markers are checked first and across both plans, because a planner that
    wrote one has stated its intent and the derivation cannot overrule it. Only then is
    `qa_only` derived, and only from a plan that parsed to at least one scenario with
    *every* one of them writing no test: a mixed list still arms the gate, which is the
    regression that matters most here.

    The derivation reads the **first** plan that carries a scenario list at all, not both.
    A layer plan with a mixed list is this layer's answer, and a root plan whose own list
    happens to be entirely QA-only must not disable the gate for it.
    """
    texts = _plan_texts(spec_abs, plan_file)
    for text in texts:
        if marker := _marker_escape(text):
            return marker
    for text in texts:
        if parse_scenarios(text):
            return _derived_escape(text)
    return ""


def declares_marker(spec_abs: Path | None, plan_file: str, marker: str) -> bool:
    """Whether either plan carries the literal marker, as opposed to only implying it.

    The escape is the same either way; this only separates *declared* from *derived* so a
    log line can say which, and a planner that keeps forgetting to write the marker down
    is visible in the run's history rather than silently compensated for.
    """
    return any(marker in text.lower() for text in _plan_texts(spec_abs, plan_file))


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
    "QA_ONLY_MARKER",
    "REGRESSION_ONLY_MARKER",
    "Scenario",
    "declares_marker",
    "escape_in_text",
    "parse_scenarios",
    "plan_escape",
    "qa_only_scenarios",
]
