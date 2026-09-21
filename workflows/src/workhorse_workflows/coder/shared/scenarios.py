"""The plan's `## 5."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from ostler import markdown

_EMPHASIS = "*_` "

_LEVEL_REASON = re.compile(r"\s+[—–]\s*|\s+-\s+|\s*[(,]")

_NO_TEST_LEVELS = {"qa-only", "qa only", "e2e", "end-to-end", "manual"}


@dataclass(frozen=True)
class Scenario:
    """One entry of the plan's scenario list, reduced to what both lanes branch on."""

    title: str
    ac: str
    level: str

    @property
    def writes_no_test(self) -> bool:
        """Whether this scenario's level means no automated test is planned for it."""
        head = _LEVEL_REASON.split(self.level, maxsplit=1)[0]
        return head.strip().lower() in _NO_TEST_LEVELS


def _words(title: str) -> list[str]:
    """A heading's words, lowercased, with a leading `5.`-style number dropped."""
    words = title.strip().lower().split()
    if words and words[0].rstrip(".").isdigit():
        words = words[1:]
    return words


def _is_scenarios_heading(title: str) -> bool:
    """Whether a heading opens the plan's scenario list — `## 5."""
    return _words(title)[:2] == ["test", "scenarios"]


def _is_scenario_heading(title: str) -> bool:
    """Whether a heading opens one scenario — `### Scenario 3: Manual fallback`."""
    return _words(title)[:1] == ["scenario"]


def _scenario_sections(doc: markdown.MarkdownDoc) -> list[markdown.Section]:
    """The sections that are scenarios of the plan's Test Scenarios list, in source order."""
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
    """Every scenario the plan's Test Scenarios section declares, with AC and level."""
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
    """The scenarios the dev plan marked as writing no test — the QA lane's obligations."""
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
