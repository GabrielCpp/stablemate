"""The book's stale report, read into the elements and files it names."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from workhorse_workflows.okf_book.catch_up.models import CURRENT, FIRST_BOOK, STALE, UNJUDGED, ModuleReport

STALE_ELEMENTS = "## Stale elements"
UNNAMED_FILES = "## Changed files no element names"
UNNAMED_FUNCTIONS = "## Changed functions no element names"
BESIDE = "## Changed beside the named symbols, functions not told apart"
GONE = "## Pointers to files that no longer exist"
ELEMENT_LINE = re.compile(r"^- (\w+): (\S+) \(\d+ commits?:")
FILE_LINE = re.compile(r"^- (\S+) \(\d+ commits?:.*?\)(?: named by (.+))?$")
VERIFIED_LINE = re.compile(r"^verified at (\S+), app at (\S+)$")
GONE_LINE = re.compile(r"^- (\w+): (\S+)$")
NOT_VERIFIED = "not verified"
NOTHING_STALE = 0
SOME_STALE = 1
COULD_NOT_READ = 2


@dataclass
class _Read:
    verified: str = ""
    elements: dict[str, list[str]] = field(default_factory=dict)
    new_files: list[str] = field(default_factory=list)
    gone: list[str] = field(default_factory=list)

    def take(self, section: str, line: str) -> None:
        """File one line of a section under what it names."""
        if section == STALE_ELEMENTS and (element := ELEMENT_LINE.match(line)):
            self.elements.setdefault(element.group(1), []).append(element.group(2))
        elif section in (UNNAMED_FILES, UNNAMED_FUNCTIONS) and (named := FILE_LINE.match(line)):
            path = named.group(1).split("::", 1)[0]
            if path not in self.new_files:
                self.new_files.append(path)
        elif section == BESIDE and (beside := FILE_LINE.match(line)) and beside.group(2):
            for name in beside.group(2).split(", "):
                self.elements.setdefault(name, []).append(beside.group(1))
        elif section == GONE and (pointer := GONE_LINE.match(line)):
            self.elements.setdefault(pointer.group(1), [])
            self.gone.append(f"{pointer.group(1)}: {pointer.group(2)}")


def read_stale(module: str, exit_code: int, stdout: str, stderr: str = "") -> ModuleReport:
    """The module's verdict from the stale command's exit code, and for a stale one the elements, files and pointers it printed."""
    if exit_code == NOTHING_STALE:
        return ModuleReport(module=module, verdict=CURRENT)
    if exit_code == COULD_NOT_READ and NOT_VERIFIED in stdout:
        return ModuleReport(module=module, verdict=FIRST_BOOK)
    if exit_code != SOME_STALE:
        return ModuleReport(module=module, verdict=UNJUDGED, output=stdout.strip(), exit_code=exit_code, error=stderr.strip())
    read = _Read()
    section = ""
    for line in stdout.splitlines():
        if found := VERIFIED_LINE.match(line):
            read.verified = found.group(1)
        elif line.startswith("## "):
            section = line
        else:
            read.take(section, line)
    return ModuleReport(module=module, verdict=STALE, verified=read.verified, elements=read.elements, new_files=read.new_files, gone=read.gone)
