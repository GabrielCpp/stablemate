"""What each command does to the repository and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Delete, Select, Transaction, Update

from ..fixtures import SCAFFOLD, InitArgs, InstallArgs, ScaffoldArgs
from . import rules
from .files import HAND_WRITTEN, SELECTED, SKILL, STARTER, FileRecord, holding
from .state import Repo

PROPOSAL = (
    "",
    "To install the base library's general and stablemate packs for every repo, add this to <sandbox>/config.toml "
    "and run `farrier install --user`:",
    "",
    "[user_library.claude]",
    'packs = ["general", "stablemate"]',
)


def write(s: Repo, path: str, *strings: str) -> Create | Update:
    """The change that leaves this file holding these strings and whatever it held before."""
    kept = s.files.get(path)
    record = holding(path, *strings, *(kept.holds if kept is not None else ()))
    return Update(s.files, path, record) if kept is not None else Create(s.files, record)


class RunInit(Action[InitArgs, Repo]):
    accept = InitArgs
    rules = (rules.not_a_directory, rules.already_configured)

    @staticmethod
    def reduce(a: InitArgs, s: Repo, by: Actor | None) -> Transaction:
        record = holding("agents.yml", *STARTER)
        change = Update(s.files, "agents.yml", record) if "agents.yml" in s.files else Create(s.files, record)
        says = ("Wrote <sandbox>/agents.yml", "Next: list this repo's own packs under `packs:`, then `farrier install`.", *PROPOSAL)
        return Transaction(change, says=says)


class RunInstall(Action[InstallArgs, Repo]):
    accept = InstallArgs
    rules = (rules.no_library_to_install, rules.missing_config)

    @staticmethod
    def reduce(a: InstallArgs, s: Repo, by: Actor | None) -> Transaction:
        config = s.files["agents.yml"]
        picked = "- demo" in config.holds
        changes: list[Create | Update | Delete] = [
            write(s, ".agents/agents.mk", "agent-install"),
            write(s, ".agents/agents-context.json", '"prefix": "acme"'),
            write(s, ".agents/agents-context.claude.json", '"prefix": "acme"'),
            write(s, ".agents/hooks/pre-commit", "No installed skill declares a pre-commit hook."),
            write(s, ".githooks/pre-commit", "make farrier-run-hook"),
            write(s, ".gitignore", ".agents/agents.mk"),
            write(s, "Makefile", "-include .agents/agents.mk"),
        ]
        if picked:
            changes.append(write(s, SKILL, "name: acme-demo", "generated_by: farrier"))
        elif SKILL in s.files:
            changes.append(Delete(s.files, SKILL))
        generated = 4 + int(picked) + int("Makefile" not in s.files)
        return Transaction(*changes, says=(f"Installed {generated} generated files into <sandbox>",))


class RunScaffold(Action[ScaffoldArgs, Repo]):
    accept = ScaffoldArgs
    rules = (rules.no_library_to_scaffold, rules.unknown_scaffold, rules.not_enabled)

    @staticmethod
    def reduce(a: ScaffoldArgs, s: Repo, by: Actor | None) -> Transaction:
        if a.name is None:
            if rules.enabled(a, s):
                return Transaction(says=(f"{SCAFFOLD} — Ignore rules for a service", "    --param dir=...  (default: api)"))
            return Transaction(says=("No scaffolds available. Library defines: service-gitignore. "
                                     f"Add ids to the `scaffolds:` list in <sandbox>/{a.at}agents.yml.",))
        folder = a.dir if a.dir is not None else "api"
        path = f"{a.at}{folder}/.gitignore"
        if path in s.files:
            made, line = 0, f"exists (kept): {folder}/.gitignore"
            changes: tuple[Create, ...] = ()
        else:
            made, line = 1, f"created: {folder}/.gitignore"
            changes = (Create(s.files, holding(path, "node_modules")),)
        return Transaction(*changes, says=(line, f"Scaffolded '{a.name}': {made} file(s) created in {a.root}"))


class ListFiles(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: f.path)


class WriteByHand(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Transaction:
        record = holding("agents.yml", *HAND_WRITTEN)
        change = Update(s.files, "agents.yml", record) if "agents.yml" in s.files else Create(s.files, record)
        return Transaction(change)


class SelectByHand(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(write(s, "agents.yml", *SELECTED))
