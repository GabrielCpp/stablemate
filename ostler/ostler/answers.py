"""The markdown Answer list a lead writes back, one answer per review finding."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Literal

from ostler import markdown

Disposition = Literal["fixed", "declined"]

DISPOSITIONS: tuple[Disposition, ...] = ("fixed", "declined")

_EMPHASIS = "*_ "


@dataclass
class Answer:
    """One finding's answer: fixed with evidence, or declined with a reason."""

    finding_id: str
    disposition: Disposition
    commits: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    reason: str = ""

    def as_dict(self) -> dict:
        """The answer as the settlement ledger records it, keyed by nothing but its fields."""
        return {"disposition": self.disposition, "commits": list(self.commits),
                "paths": list(self.paths), "tests": list(self.tests), "reason": self.reason}


@dataclass
class AnswerList:
    """Every well-formed answer, and one human-readable error per answer that is not."""

    answers: list[Answer] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def by_id(self) -> dict[str, Answer]:
        """The answers keyed by finding id."""
        return {answer.finding_id: answer for answer in self.answers}


@dataclass
class _Entry:
    finding_id: str
    answer: Answer | None
    error: str


def _unquoted(text: str) -> str:
    return text.strip().strip("`").strip()


def _heading(section: markdown.Section) -> _Entry:
    title = section.title.strip()
    finding_id, sep, rest = title.partition(":")
    finding_id = _unquoted(finding_id)
    disposition = rest.strip().lower()
    if not sep or not finding_id or any(ch.isspace() for ch in finding_id) or not disposition:
        return _Entry(finding_id if sep and finding_id else "", None,
                      f"malformed answer heading '## {title}': expected "
                      "'## <finding-id>: fixed' or '## <finding-id>: declined'")
    if disposition not in DISPOSITIONS:
        return _Entry(finding_id, None,
                      f"{finding_id}: unknown disposition '{disposition}' "
                      "(expected fixed or declined)")
    answer = Answer(finding_id, "fixed" if disposition == "fixed" else "declined")
    _collect_evidence(section, answer)
    answer.reason = _reason(section)
    if answer.disposition == "fixed" and not (answer.commits or answer.paths or answer.tests):
        return _Entry(finding_id, None,
                      f"{finding_id}: a fixed answer cites no evidence "
                      "('- commit: ', '- path: ' or '- test: ')")
    if answer.disposition == "declined" and not answer.reason:
        return _Entry(finding_id, None,
                      f"{finding_id}: a declined answer gives no reason ('Reason: ')")
    return _Entry(finding_id, answer, "")


def _collect_evidence(section: markdown.Section, answer: Answer) -> None:
    targets = {"commit": answer.commits, "path": answer.paths, "test": answer.tests}
    for sub in section.walk():
        for top in sub.bullets:
            for bullet in top.walk():
                bucket = targets.get(bullet.label)
                value = _unquoted(bullet.value)
                if bucket is not None and value:
                    bucket.append(value)


def _reason_start(line: str) -> str | None:
    """The text after a ``Reason:`` label on *line*, or ``None`` when the line carries none."""
    stripped = line.strip()
    idx = markdown.label_colon_index(stripped)
    if idx == -1 or stripped[:idx].strip().strip(_EMPHASIS).lower() != "reason":
        return None
    return stripped[idx + 1:].lstrip(_EMPHASIS)


def _reason(section: markdown.Section) -> str:
    lines = section.body.split("\n")
    for i, line in enumerate(lines):
        first = _reason_start(line)
        if first is not None:
            return "\n".join([first, *lines[i + 1:]]).strip()
    for sub in section.walk():
        for top in sub.bullets:
            for bullet in top.walk():
                if bullet.label == "reason" and bullet.value:
                    return bullet.value
    return ""


def parse_answers(text: str) -> AnswerList:
    """Parse a markdown Answer list: one ``## <finding-id>: fixed|declined`` section per finding."""
    doc = markdown.split(text)
    entries = [_heading(section) for section in doc.walk_sections() if section.level == 2]
    counts = Counter(entry.finding_id for entry in entries if entry.finding_id)
    result = AnswerList()
    reported: set[str] = set()
    for entry in entries:
        if entry.finding_id and counts[entry.finding_id] > 1:
            if entry.finding_id not in reported:
                reported.add(entry.finding_id)
                result.errors.append(f"{entry.finding_id}: answered "
                                     f"{counts[entry.finding_id]} times; answer each finding once")
            continue
        if entry.error:
            result.errors.append(entry.error)
        elif entry.answer is not None:
            result.answers.append(entry.answer)
    return result
