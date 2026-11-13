"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import ClassVar

from ostler.book import Mark

NAMES = ("loop-runner", "research", "author", "coder", "okf-book", "review-debt")
RUN = '"workflow": "{}"'
SUBFLOWS = ("Finalize", "BookQa", "Dev", "Docs", "Fix", "Qa")
SKILLS = ("ostler-book",)
SKILL_NAME = "name: {}"
CHECKS = ("pytest -q", "make test")

MARKS = (
    Mark(".agents/runs/*/run.json", *(RUN.format(n) for n in (*NAMES, *SUBFLOWS))),
    Mark(".claude/skills/*/SKILL.md", *(SKILL_NAME.format(s) for s in SKILLS)),
    Mark("*fix-tests/pyproject.toml", 'name = "fix-tests"', 'workhorse-fix-tests = "fix_tests.workflow:main"'),
    Mark("*fix-tests/README.md", "# fix-tests", *(f"`{c}`" for c in CHECKS)),
    Mark("*fix-tests/src/fix_tests/__init__.py", "`workhorse-fix-tests`"),
    Mark("*fix-tests/src/fix_tests/workflow.py", *(f'check: str = "{c}"' for c in CHECKS)),
    Mark("*fix-tests/src/fix_tests/prompts/fix.md", "Fix the cause, not the check."),
)

TREE = (
    "pyproject.toml",
    "README.md",
    "src/fix_tests/__init__.py",
    "src/fix_tests/workflow.py",
    "src/fix_tests/prompts/fix.md",
)


@dataclass(frozen=True)
class FileRecord:
    """A watched file the sandbox holds."""

    path: str
    holds: tuple[str, ...] = ()

    source: ClassVar[tuple[str, ...]] = (
        "workflows/src/workhorse_workflows/new/scaffold.py::scaffold",
        "workhorse/workhorse/pyflow/run.py::run_pyflow",
    )

    def __str__(self) -> str:
        return f"{self.path} [{'; '.join(self.holds)}]"


def declared(path: str) -> tuple[str, ...]:
    """The strings the watch looks for in this path, in the order it lists them."""
    return tuple(dict.fromkeys(s for m in MARKS if fnmatch.fnmatchcase(path, m.glob) for s in m.holds))


def holding(path: str, *strings: str) -> FileRecord:
    """The record of a file that holds these strings, in the order the watch lists them."""
    return FileRecord(path, tuple(s for s in declared(path) if s in strings))
