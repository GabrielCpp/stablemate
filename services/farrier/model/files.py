"""The files the book watches and what the model keeps for each: its path and
which of the declared strings it holds. A row is that and nothing more."""

from __future__ import annotations

from typing import ClassVar

from ostler.book import Mark, Watched

STARTER = ("# agents.yml — what farrier renders", "claude: true", "packs: []")
HAND_WRITTEN = ("# hand-written", "claude: true")
SELECTED = ("- demo", "- service-gitignore")
CONTEXT = '"prefix": "acme"'
SKILL = ".claude/skills/acme-demo/SKILL.md"
HOME_SKILL = "home/.claude/skills/demo/SKILL.md"
CONFIG = "config.toml"
USER_LIBRARY = "[user_library.claude]"
SETTINGS = {
    "library_dir": 'library_dir = "',
    "base_dir": 'base_dir = "',
    "stablemate_dir": 'stablemate_dir = "',
    "worktree_dir": 'worktree_dir = "',
    "default_cli": 'default_cli = "codex"',
}
SETTING_VALUES = {
    "library_dir": "<sandbox>/lib",
    "base_dir": "<sandbox>/lib",
    "stablemate_dir": "<sandbox>/st",
    "worktree_dir": "<sandbox>/wt",
    "default_cli": "codex",
}

MARKS = (
    Mark(CONFIG, *SETTINGS.values(), USER_LIBRARY),
    Mark("agents.yml", "# hand-written", *STARTER, *SELECTED),
    Mark("Makefile", "-include .agents/agents.mk"),
    Mark(".gitignore", ".agents/agents.mk"),
    Mark(".githooks/pre-commit", "make farrier-run-hook"),
    Mark(".agents/agents.mk", "agent-install"),
    Mark(".agents/agents-context.json", CONTEXT),
    Mark(".agents/agents-context.claude.json", CONTEXT),
    Mark(".agents/hooks/pre-commit", "No installed skill declares a pre-commit hook."),
    Mark(".agents/hooks/commit-msg", "No installed skill declares a commit-msg hook."),
    Mark(".claude/skills/*/SKILL.md", "name: acme-demo", "generated_by: farrier"),
    Mark(HOME_SKILL, "name: demo", "generated_by: farrier"),
    Mark("*/.gitignore", "node_modules"),
)


class FileRecord(Watched):
    """A watched file the sandbox holds."""

    marks = MARKS
    source: ClassVar[tuple[str, ...]] = ("farrier/farrier/outputs.py::write_text",)
