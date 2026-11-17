"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

from typing import ClassVar

from ostler.book import Mark, Watched

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


class FileRecord(Watched):
    """A watched file the sandbox holds."""

    marks = MARKS
    source: ClassVar[tuple[str, ...]] = (
        "workflows/src/workhorse_workflows/new/scaffold.py::scaffold",
        "workhorse/workhorse/pyflow/run.py::run_pyflow",
    )
