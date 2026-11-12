"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from typing import ClassVar

from ostler.book import Mark

STARTER = ("# agents.yml — what farrier renders", "claude: true", "packs: []")
HAND_WRITTEN = ("# hand-written", "claude: true")
SELECTED = ("- demo", "- service-gitignore")
CONTEXT = '"prefix": "acme"'
SKILL = ".claude/skills/acme-demo/SKILL.md"

MARKS = (
    Mark("agents.yml", "# hand-written", *STARTER, *SELECTED),
    Mark("Makefile", "-include .agents/agents.mk"),
    Mark(".gitignore", ".agents/agents.mk"),
    Mark(".githooks/pre-commit", "make farrier-run-hook"),
    Mark(".agents/agents.mk", "agent-install"),
    Mark(".agents/agents-context.json", CONTEXT),
    Mark(".agents/agents-context.claude.json", CONTEXT),
    Mark(".agents/hooks/pre-commit", "No installed skill declares a pre-commit hook."),
    Mark(".claude/skills/*/SKILL.md", "name: acme-demo", "generated_by: farrier"),
    Mark("*/.gitignore", "node_modules"),
)


@dataclass(frozen=True)
class FileRecord:
    """A watched file the sandbox holds."""

    path: str
    holds: tuple[str, ...] = ()

    source: ClassVar[tuple[str, ...]] = ("farrier/farrier/outputs.py::write_text",)

    def __str__(self) -> str:
        return f"{self.path} [{'; '.join(self.holds)}]"


def declared(path: str) -> tuple[str, ...]:
    """The strings the watch looks for in this path, in the order it lists them."""
    return tuple(dict.fromkeys(s for m in MARKS if fnmatch.fnmatchcase(path, m.glob) for s in m.holds))


def holding(path: str, *strings: str) -> FileRecord:
    """The record of a file that holds these strings, in the order the watch lists them."""
    return FileRecord(path, tuple(s for s in declared(path) if s in strings))
