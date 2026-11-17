"""Why farrier says no. The message is the one it prints, word for word, with
the sandbox written `<sandbox>`. A rule reads the request (`a`) and the
repository (`s`)."""

from __future__ import annotations

from ostler.book import Actor, Exited, Rule

from ..fixtures import (GENERATED, LIBRARY, SCAFFOLD, SKILL_NAME, BaseDirArgs, ConfigGetArgs, ConfigReferenceArgs,
                        ConfigSetArgs, ConfigShowArgs, DoctorArgs, EjectArgs, HooksListArgs, InitArgs, InstallArgs,
                        InstallUserArgs, LibraryCheckArgs, LibraryDirArgs, LibraryListArgs, LibraryShowArgs,
                        ScaffoldArgs, SourceArgs)
from .files import CONFIG, SETTINGS, USER_LIBRARY
from .state import Repo

MACHINE_KEYS = ("config_version", *SETTINGS)
UNSET_WITHOUT_DEFAULT = ("library_dir", "base_dir", "stablemate_dir", "worktree_dir")

FAILED = Exited(1)


def _no_directory(a: InitArgs, s: Repo, by: Actor | None) -> bool:
    return not a.here


def _already_configured(a: InitArgs, s: Repo, by: Actor | None) -> bool:
    return "agents.yml" in s.files and not a.force


def _no_library(a: InstallArgs | ScaffoldArgs, s: Repo, by: Actor | None) -> bool:
    return a.library != LIBRARY


def _no_config(a: InstallArgs, s: Repo, by: Actor | None) -> bool:
    return not a.here or "agents.yml" not in s.files


def _unknown_scaffold(a: ScaffoldArgs, s: Repo, by: Actor | None) -> bool:
    return a.name is not None and a.name != SCAFFOLD


def enabled(a: ScaffoldArgs, s: Repo) -> bool:
    """Whether the repository lists the scaffold: it has no agents.yml to refuse it, or the file names it."""
    config = s.files.get("agents.yml") if a.here else None
    return config is None or "- service-gitignore" in config.holds


def _not_enabled(a: ScaffoldArgs, s: Repo, by: Actor | None) -> bool:
    return a.name is not None and not enabled(a, s)


not_a_directory = Rule[InitArgs, Repo]("error: <sandbox>/{repo} is not a directory", _no_directory, FAILED)
already_configured = Rule[InitArgs, Repo](
    "error: <sandbox>/agents.yml already exists — this repo is configured; run `farrier install --repo {typed}` to render it, "
    "or `farrier init --force` to replace the config with a fresh default", _already_configured, FAILED,
    why="init is the one command that runs before a repo is configured, so it never replaces a config unasked.")
no_library_to_install = Rule[InstallArgs, Repo](
    "error: <sandbox>/{library} (from --library) is not a usable library directory — it must contain library/.",
    _no_library, FAILED)
missing_config = Rule[InstallArgs, Repo](
    "Missing config: <sandbox>/{at}agents.yml\n"
    "Run `farrier init` to write a starter agents.yml, then list the packs to install under `packs:`.", _no_config, FAILED)
no_library_to_scaffold = Rule[ScaffoldArgs, Repo](
    "error: <sandbox>/{library} (from --library) is not a usable library directory — it must contain library/.",
    _no_library, FAILED)
unknown_scaffold = Rule[ScaffoldArgs, Repo]("Unknown scaffold: '{name}'. Library defines: service-gitignore", _unknown_scaffold, FAILED)
not_enabled = Rule[ScaffoldArgs, Repo](
    "Scaffold '{name}' is not enabled for this repo — add it to the `scaffolds:` list in <sandbox>/{at}agents.yml "
    "(or select a pack that provides it).", _not_enabled, FAILED)


def configured(s: Repo, key: str) -> bool:
    """Whether the home config sets this key."""
    return key == "config_version" or SETTINGS[key] in s.files[CONFIG].holds


def has_library(s: Repo) -> bool:
    """Whether the home config names a library directory or a base to resolve one from."""
    return configured(s, "library_dir") or configured(s, "base_dir")


def generated_skill(s: Repo) -> bool:
    """Whether the repository holds the skill install generated."""
    skill = s.files.get(".claude/skills/acme-demo/SKILL.md")
    return skill is not None and "generated_by: farrier" in skill.holds


def _no_agents_to_diagnose(a: DoctorArgs, s: Repo, by: Actor | None) -> bool:
    return not a.here or "agents.yml" not in s.files


def _no_agents_to_list(a: HooksListArgs, s: Repo, by: Actor | None) -> bool:
    return not a.here or "agents.yml" not in s.files


def _unknown_key(a: ConfigGetArgs | ConfigReferenceArgs, s: Repo, by: Actor | None) -> bool:
    return a.key not in MACHINE_KEYS


def _unset_get(a: ConfigGetArgs, s: Repo, by: Actor | None) -> bool:
    return a.key in UNSET_WITHOUT_DEFAULT and not configured(s, a.key)


def _unset_show(a: ConfigShowArgs, s: Repo, by: Actor | None) -> bool:
    return a.key is not None and (a.key not in MACHINE_KEYS or not configured(s, a.key))


def _no_equals(a: ConfigSetArgs, s: Repo, by: Actor | None) -> bool:
    return "=" not in (a.assignment or "") or a.setting == ""


def _unknown_setting(a: ConfigSetArgs, s: Repo, by: Actor | None) -> bool:
    return "=" in (a.assignment or "") and a.setting != "" and a.setting not in MACHINE_KEYS


def _no_library_to_set(a: LibraryDirArgs, s: Repo, by: Actor | None) -> bool:
    return a.path != LIBRARY


def _no_base_to_set(a: BaseDirArgs, s: Repo, by: Actor | None) -> bool:
    return a.path != LIBRARY


def _no_library_flag(a: LibraryListArgs | LibraryShowArgs | LibraryCheckArgs | SourceArgs | EjectArgs | InstallUserArgs,
                     s: Repo, by: Actor | None) -> bool:
    return a.library != LIBRARY


def _show_needs_one(a: LibraryShowArgs, s: Repo, by: Actor | None) -> bool:
    return not a.skill


def _unknown_skill(a: LibraryShowArgs, s: Repo, by: Actor | None) -> bool:
    return bool(a.skill) and a.skill != "demo"


def _not_a_file(a: SourceArgs, s: Repo, by: Actor | None) -> bool:
    return a.file not in s.files


def _not_generated(a: SourceArgs, s: Repo, by: Actor | None) -> bool:
    return not (a.file == GENERATED and generated_skill(s))


def _eject_without_config(a: EjectArgs, s: Repo, by: Actor | None) -> bool:
    return "agents.yml" not in s.files


def _nothing_to_eject(a: EjectArgs, s: Repo, by: Actor | None) -> bool:
    return not generated_skill(s)


def _not_that_one(a: EjectArgs, s: Repo, by: Actor | None) -> bool:
    return generated_skill(s) and a.name != SKILL_NAME


def _no_user_library(a: InstallUserArgs, s: Repo, by: Actor | None) -> bool:
    return USER_LIBRARY not in s.files[CONFIG].holds


NO_KEY = "`{key}` is not a machine-config key. `farrier config reference --file home` lists every key."
NO_LIBRARY_DIR = "<sandbox>/{library} (from --library) is not a usable library directory — it must contain library/."
NEITHER = "'{name}' is neither a farrier-generated skill folder nor a policy listed in localInstructions."

doctor_without_config = Rule[DoctorArgs, Repo](
    "error: no agents.yml in {typed} — run `farrier init` to write a starter one.\n\n1 error(s), 0 warning(s).",
    _no_agents_to_diagnose, FAILED)
hooks_list_without_config = Rule[HooksListArgs, Repo](
    "error: no agents.yml in {root} — run 'farrier init' to write one.", _no_agents_to_list, FAILED)
unknown_key_to_get = Rule[ConfigGetArgs, Repo]("error: " + NO_KEY, _unknown_key, FAILED)
unset_to_get = Rule[ConfigGetArgs, Repo](
    "error: `{key}` is not set in <sandbox>/config.toml and has no default", _unset_get, FAILED)
unset_to_show = Rule[ConfigShowArgs, Repo]("error: '{key}' is not set in <sandbox>/config.toml", _unset_show, FAILED)
set_without_equals = Rule[ConfigSetArgs, Repo]("error: expected KEY=VALUE, got `{assignment}`", _no_equals, FAILED)
unknown_setting = Rule[ConfigSetArgs, Repo]("error: `{setting}` is not a machine-config key. `farrier config reference --file home` lists every key.",
                                            _unknown_setting, FAILED)
unknown_key_to_describe = Rule[ConfigReferenceArgs, Repo](
    "error: no config key matches `{key}`. `farrier config reference` lists every key.", _unknown_key, FAILED)
not_a_library_to_set = Rule[LibraryDirArgs, Repo](
    "error: <sandbox>/{path} is not a usable library directory — it must contain library/ and packs/.",
    _no_library_to_set, FAILED,
    why="the check is for library/ alone, so a directory with no packs/ is accepted: see DISAGREEMENTS 1.")
not_a_base_to_set = Rule[BaseDirArgs, Repo](
    "error: <sandbox>/{path} is not a usable base library directory — it must contain library/.", _no_base_to_set, FAILED)
no_library_to_list = Rule[LibraryListArgs, Repo]("error: " + NO_LIBRARY_DIR, _no_library_flag, FAILED)
no_library_to_check = Rule[LibraryCheckArgs, Repo]("error: " + NO_LIBRARY_DIR, _no_library_flag, FAILED)
no_library_to_show = Rule[LibraryShowArgs, Repo]("error: " + NO_LIBRARY_DIR, _no_library_flag, FAILED)
show_needs_one = Rule[LibraryShowArgs, Repo](
    "error: `farrier library show` takes exactly one of: --skill NAME | --prompt NAME | --policy NAME | --pack NAME | "
    "--scaffold NAME | --root NAME", _show_needs_one, FAILED)
no_such_skill = Rule[LibraryShowArgs, Repo](
    "error: no skill named '{skill}'. The stack provides:\n  - demo", _unknown_skill, FAILED)
source_not_a_file = Rule[SourceArgs, Repo]("error: {file} is not a file", _not_a_file, FAILED)
no_library_for_source = Rule[SourceArgs, Repo]("error: " + NO_LIBRARY_DIR, _no_library_flag, FAILED)
not_generated = Rule[SourceArgs, Repo](
    "error: {file} has no `metadata.source` front matter and no farrier banner — it is not a farrier-generated file.",
    _not_generated, FAILED)
no_library_to_eject = Rule[EjectArgs, Repo]("error: " + NO_LIBRARY_DIR, _no_library_flag, FAILED)
eject_without_config = Rule[EjectArgs, Repo]("Missing config: <sandbox>/agents.yml", _eject_without_config, FAILED)
nothing_to_eject = Rule[EjectArgs, Repo](
    "error: " + NEITHER + "\nEjectable skills: (none)\nEjectable policies: (none)", _nothing_to_eject, FAILED)
not_that_skill = Rule[EjectArgs, Repo](
    "error: " + NEITHER + "\nEjectable skills: acme-demo\nEjectable policies: (none)", _not_that_one, FAILED)
no_library_for_user = Rule[InstallUserArgs, Repo]("error: " + NO_LIBRARY_DIR, _no_library_flag, FAILED)
no_user_library = Rule[InstallUserArgs, Repo](
    "error: no user library is configured. Add a [user_library.<harness>] table naming the skills to install for every "
    "project — one of claude, codex, copilot, opencode — to <sandbox>/config.toml.", _no_user_library, FAILED)
