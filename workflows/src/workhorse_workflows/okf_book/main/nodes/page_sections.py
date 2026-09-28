"""The sections of a page, each `###` node with the lines under it, and the section each problem on the page sits in.

A page too large for one writer is repaired a few sections at a time. A section runs from its `###`
heading to the next heading of level three or above. The lines under no `###` heading, such as the
page's front matter and the prose under a `##` heading, are its head, named by the empty id.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from workhorse_workflows.okf_book.shared.page_check import PageProblem

HEAD = ""
_FENCE = "```"
_BOUNDARY = re.compile(r"^#{1,3} ")
_NODE = re.compile(r"^### +(?P<id>.+?)\s*$")


@dataclass(frozen=True, slots=True)
class Section:
    """One `###` node of a page, or the page's head, and the 1-based line numbers it holds."""

    id: str
    line_numbers: tuple[int, ...]


def _anchor(heading: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")


@dataclass(frozen=True, slots=True)
class PageSections:
    """A page's sections, in page order, and the text of each."""

    text: str
    sections: tuple[Section, ...]

    def section_text(self, section: Section) -> str:
        lines = self.text.splitlines()
        return "".join(lines[number - 1] + "\n" for number in section.line_numbers)

    def by_id(self, section_id: str) -> Section | None:
        return next((section for section in self.sections if section.id == section_id), None)

    def section_id_of_problem(self, problem: PageProblem) -> str:
        """The id of the section a problem on this page sits in: the node it names, else the line it names, else the head."""
        anchor = problem.node.partition("#")[2]
        named = next((section.id for section in self.sections if section.id != HEAD and _anchor(section.id) == anchor), None)
        if anchor and named is not None:
            return named
        if problem.line is not None:
            return next((section.id for section in self.sections if problem.line in section.line_numbers), HEAD)
        return HEAD


def page_sections(text: str) -> PageSections:
    """Split a page into its head and its `###` nodes. A heading inside a fenced block splits nothing."""
    owner: list[str] = []
    current = HEAD
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith(_FENCE):
            fenced = not fenced
        elif not fenced and _BOUNDARY.match(line):
            node = _NODE.match(line)
            current = node.group("id") if node else HEAD
        owner.append(current)
    ids = list(dict.fromkeys([HEAD, *owner]))
    sections = tuple(
        Section(section_id, tuple(number for number, holder in enumerate(owner, start=1) if holder == section_id))
        for section_id in ids
    )
    return PageSections(text, tuple(section for section in sections if section.line_numbers or section.id == HEAD))
