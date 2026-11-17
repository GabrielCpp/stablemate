"""What each command does to the repository and what it prints."""

from __future__ import annotations

from ostler.book import Action, Actor, Create, Delete, Select, Transaction, Update

from ..fixtures import (HOME, SCAFFOLD, BaseDirArgs, ChecksArgs, ConfigGetArgs, ConfigReferenceArgs, ConfigSetArgs,
                        ConfigShowArgs, DoctorArgs, EjectArgs, HooksInstallArgs, HooksListArgs, InitArgs, InstallArgs,
                        InstallUserArgs, LibraryCheckArgs, LibraryDirArgs, LibraryListArgs, LibraryShowArgs,
                        ScaffoldArgs, SourceArgs, StablemateDirArgs, SyncArgs, VersionArgs, WorkflowNamesArgs,
                        WorkflowsArgs, WorktreeDirArgs, WorktreesArgs)
from . import rules
from .files import (CONFIG, HAND_WRITTEN, HOME_SKILL, SELECTED, SETTING_VALUES, SETTINGS, SKILL, STARTER, USER_LIBRARY,
                    FileRecord)
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
    record = FileRecord.holding(path, *strings, *(kept.holds if kept is not None else ()))
    return Update(s.files, path, record) if kept is not None else Create(s.files, record)


class RunInit(Action[InitArgs, Repo]):
    accept = InitArgs
    rules = (rules.not_a_directory, rules.already_configured)

    @staticmethod
    def reduce(a: InitArgs, s: Repo, by: Actor | None) -> Transaction:
        record = FileRecord.holding("agents.yml", *STARTER)
        change = Update(s.files, "agents.yml", record) if "agents.yml" in s.files else Create(s.files, record)
        proposal = () if USER_LIBRARY in s.files[CONFIG].holds else PROPOSAL
        says = ("Wrote <sandbox>/agents.yml", "Next: list this repo's own packs under `packs:`, then `farrier install`.", *proposal)
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
            write(s, ".agents/hooks/commit-msg", "No installed skill declares a commit-msg hook."),
            write(s, ".githooks/pre-commit", "make farrier-run-hook"),
            write(s, ".gitignore", ".agents/agents.mk"),
            write(s, "Makefile", "-include .agents/agents.mk"),
        ]
        if picked:
            changes.append(write(s, SKILL, "name: acme-demo", "generated_by: farrier"))
        elif SKILL in s.files and "generated_by: farrier" in s.files[SKILL].holds:
            changes.append(Delete(s.files, SKILL))
        generated = 5 + int(picked) + int("Makefile" not in s.files)
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
            changes = (Create(s.files, FileRecord.holding(path, "node_modules")),)
        return Transaction(*changes, says=(line, f"Scaffolded '{a.name}': {made} file(s) created in {a.root}"))


class ListFiles(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Select[FileRecord]:
        return Select(s.files, order=lambda f: f.path)


class WriteByHand(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Transaction:
        record = FileRecord.holding("agents.yml", *HAND_WRITTEN)
        change = Update(s.files, "agents.yml", record) if "agents.yml" in s.files else Create(s.files, record)
        return Transaction(change)


class SelectByHand(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(write(s, "agents.yml", *SELECTED))


class RunVersion(Action[VersionArgs, Repo]):
    accept = VersionArgs

    @staticmethod
    def reduce(a: VersionArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction()


class RunDoctor(Action[DoctorArgs, Repo]):
    accept = DoctorArgs
    rules = (rules.doctor_without_config,)

    @staticmethod
    def reduce(a: DoctorArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=(
            "warning: no services: block — the dev lane will skip every gate. Declare the commands that check a service, "
            "keyed by its name or its type:",
            "    services:", "      <service-or-type>:", "        lint: <command>", "        test: <command>",
            "", "0 error(s), 1 warning(s).",
        ))


def set_in_config(s: Repo, *keys: str) -> Create | Update:
    """The change that leaves these settings in the home config beside the ones it already holds."""
    kept = s.files[CONFIG]
    return Update(s.files, CONFIG, FileRecord.holding(CONFIG, *(SETTINGS[k] for k in keys), *kept.holds))


def values_set(s: Repo) -> tuple[str, ...]:
    """The keys the home config sets, in the order the tool lists them."""
    return tuple(k for k in SETTINGS if k != "default_cli" and rules.configured(s, k)) + (
        ("default_cli",) if rules.configured(s, "default_cli") else ())


class RunConfigShow(Action[ConfigShowArgs, Repo]):
    accept = ConfigShowArgs
    rules = (rules.unset_to_show,)

    @staticmethod
    def reduce(a: ConfigShowArgs, s: Repo, by: Actor | None) -> Transaction:
        if a.key == "config_version":
            return Transaction(says=("2",))
        if a.key is not None:
            return Transaction(says=(SETTING_VALUES[a.key],))
        table = ("user_library={'claude': {'skills': ['demo']}}",) if USER_LIBRARY in s.files[CONFIG].holds else ()
        return Transaction(says=("config_version=2", *(f"{k}={SETTING_VALUES[k]}" for k in values_set(s)), *table))


class RunConfigGet(Action[ConfigGetArgs, Repo]):
    accept = ConfigGetArgs
    rules = (rules.unknown_key_to_get, rules.unset_to_get)

    @staticmethod
    def reduce(a: ConfigGetArgs, s: Repo, by: Actor | None) -> Transaction:
        if a.key == "config_version":
            return Transaction(says=("2",))
        if a.key == "default_cli" and not rules.configured(s, "default_cli"):
            return Transaction(says=("claude",))
        assert a.key is not None
        return Transaction(says=(SETTING_VALUES[a.key],))


class RunConfigSet(Action[ConfigSetArgs, Repo]):
    accept = ConfigSetArgs
    rules = (rules.set_without_equals, rules.unknown_setting)

    @staticmethod
    def reduce(a: ConfigSetArgs, s: Repo, by: Actor | None) -> Transaction:
        value = (a.assignment or "").partition("=")[2]
        change = (set_in_config(s, "default_cli"),) if a.setting == "default_cli" and value == "codex" else ()
        return Transaction(*change, says=(a.assignment,))


class RunConfigReference(Action[ConfigReferenceArgs, Repo]):
    accept = ConfigReferenceArgs
    rules = (rules.unknown_key_to_describe,)

    @staticmethod
    def reduce(a: ConfigReferenceArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction()


class RunSetWorktree(Action[WorktreeDirArgs, Repo]):
    accept = WorktreeDirArgs

    @staticmethod
    def reduce(a: WorktreeDirArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(set_in_config(s, "worktree_dir"), says=(f"worktree_dir=<sandbox>/{a.path}",))


class RunSetStablemate(Action[StablemateDirArgs, Repo]):
    accept = StablemateDirArgs

    @staticmethod
    def reduce(a: StablemateDirArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(set_in_config(s, "stablemate_dir"), says=(f"stablemate_dir=<sandbox>/{a.path}",))


class RunSetLibrary(Action[LibraryDirArgs, Repo]):
    accept = LibraryDirArgs
    rules = (rules.not_a_library_to_set,)

    @staticmethod
    def reduce(a: LibraryDirArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(set_in_config(s, "library_dir"), says=(f"library_dir=<sandbox>/{a.path}",))


class RunSetBase(Action[BaseDirArgs, Repo]):
    accept = BaseDirArgs
    rules = (rules.not_a_base_to_set,)

    @staticmethod
    def reduce(a: BaseDirArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(set_in_config(s, "base_dir"), says=(f"base_dir=<sandbox>/{a.path}",))


CATALOG = (
    "# layer: <sandbox>/lib", "",
    "## skills (1)", "  demo  demo  <sandbox>/lib", "",
    "## prompts (0)", "  (none)", "",
    "## policies (0)", "  (none)", "",
    "## packs (0)", "  (none)", "",
    "## scaffolds (1)", "  service-gitignore  <sandbox>/lib", "",
    "## roots (0)", "  (none)",
)
DEMO_SOURCE = ("---", "name: demo", 'description: "A skill."', "---", "", "Use it.")


class RunLibraryList(Action[LibraryListArgs, Repo]):
    accept = LibraryListArgs
    rules = (rules.no_library_to_list,)

    @staticmethod
    def reduce(a: LibraryListArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=CATALOG)


class RunLibraryShow(Action[LibraryShowArgs, Repo]):
    accept = LibraryShowArgs
    rules = (rules.no_library_to_show, rules.show_needs_one, rules.no_such_skill)

    @staticmethod
    def reduce(a: LibraryShowArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=DEMO_SOURCE)


class RunLibraryCheck(Action[LibraryCheckArgs, Repo]):
    accept = LibraryCheckArgs
    rules = (rules.no_library_to_check,)

    @staticmethod
    def reduce(a: LibraryCheckArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=("# layer: <sandbox>/lib", "ok: 1 library sources, all front matter parses"))


class RunSource(Action[SourceArgs, Repo]):
    accept = SourceArgs
    rules = (rules.source_not_a_file, rules.no_library_for_source, rules.not_generated)

    @staticmethod
    def reduce(a: SourceArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=("<sandbox>/lib/library/skills/demo.md",))


class RunEject(Action[EjectArgs, Repo]):
    accept = EjectArgs
    rules = (rules.no_library_to_eject, rules.eject_without_config, rules.nothing_to_eject, rules.not_that_skill)

    @staticmethod
    def reduce(a: EjectArgs, s: Repo, by: Actor | None) -> Transaction:
        config = s.files["agents.yml"]
        released = FileRecord.holding("agents.yml", *(h for h in config.holds if h != "- demo"))
        kept = FileRecord.holding(SKILL, "name: acme-demo")
        changes: list[Create | Update | Delete] = [
            Update(s.files, "agents.yml", released),
            Update(s.files, SKILL, kept),
        ]
        return Transaction(*changes, says=(
            "Ejected skill 'acme-demo': .claude/skills/acme-demo is now yours, and agents.yml no longer selects demo.",
            "Installed 5 generated files into <sandbox>",
        ))


class RunHooksList(Action[HooksListArgs, Repo]):
    accept = HooksListArgs
    rules = (rules.hooks_list_without_config,)

    @staticmethod
    def reduce(a: HooksListArgs, s: Repo, by: Actor | None) -> Transaction:
        if rules.has_library(s):
            return Transaction(says=("pre-commit:", "  (none)", "commit-msg:", "  (none)"))
        return Transaction(says=("no library available — set one with 'farrier config set-library <dir>'.",))


class RunHooksInstall(Action[HooksInstallArgs, Repo]):
    accept = HooksInstallArgs

    @staticmethod
    def reduce(a: HooksInstallArgs, s: Repo, by: Actor | None) -> Transaction:
        final = "hooks wired through: githooks"
        if a.dry_run:
            return Transaction(says=(
                "[dry-run] would set executable bit on .githooks/pre-commit",
                "[dry-run] would set executable bit on .githooks/commit-msg",
                "[dry-run] would set core.hooksPath to .githooks",
                "[dry-run] would regenerate .agents/hooks/pre-commit, .agents/hooks/commit-msg "
                "(no library — run 'farrier install' to refresh)",
                final,
            ))
        return Transaction(write(s, ".githooks/pre-commit", "make farrier-run-hook"), says=(final,))


class RunChecks(Action[ChecksArgs, Repo]):
    accept = ChecksArgs

    @staticmethod
    def reduce(a: ChecksArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction()


class RunSync(Action[SyncArgs, Repo]):
    accept = SyncArgs

    @staticmethod
    def reduce(a: SyncArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction()


class RunInstallUser(Action[InstallUserArgs, Repo]):
    accept = InstallUserArgs
    rules = (rules.no_library_for_user, rules.no_user_library)

    @staticmethod
    def reduce(a: InstallUserArgs, s: Repo, by: Actor | None) -> Transaction:
        changes = (write(s, HOME_SKILL, "name: demo", "generated_by: farrier"),) if a.home == HOME else ()
        return Transaction(*changes, says=(f"Installed 1 generated files into <sandbox>/{a.home}",))


class RunWorkflows(Action[WorkflowsArgs, Repo]):
    accept = WorkflowsArgs

    @staticmethod
    def reduce(a: WorkflowsArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=("No workflows installed. Install a workflow distribution "
                                 "(e.g. `pipx install workhorse-workflows`) and they appear here.",))


class RunWorkflowNames(Action[WorkflowNamesArgs, Repo]):
    accept = WorkflowNamesArgs

    @staticmethod
    def reduce(a: WorkflowNamesArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction(says=("",))


class RunWorktrees(Action[WorktreesArgs, Repo]):
    accept = WorktreesArgs

    @staticmethod
    def reduce(a: WorktreesArgs, s: Repo, by: Actor | None) -> Transaction:
        return Transaction()


class AddUserLibrary(Action[object, Repo]):
    @staticmethod
    def reduce(a: object, s: Repo, by: Actor | None) -> Transaction:
        kept = s.files[CONFIG]
        return Transaction(Update(s.files, CONFIG, FileRecord.holding(CONFIG, USER_LIBRARY, *kept.holds)))
