"""The farrier commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Files, Flag, Lines, Object, Positional, Str, Switch

from .model import actions as act
from .model.actions import ListFiles, RunInit, RunInstall, RunScaffold
from .model.files import MARKS

OPAQUE = ("Updated .agents", "Wired ", "Added agent launcher", "info: ")
CLI = "farrier/farrier/cli.py"

REPO = Field(Str(classes={"a directory that does not exist": "no-such-dir"}), required=False,
             does="the repository root; the working directory when left out")
LIBRARY = Field(Str(classes={"a library that does not exist": "no-such-lib"}), required=False,
                does="the library directory, which must hold library/")


class Init(Command):
    does = "Write a starter agents.yml so this repository can be configured."
    program = "farrier"
    argv = ("init", Flag("--repo", "repo"), Switch("--force", "force"))
    args = Object("InitArgs", repo=REPO, force=Field(Bool(), required=False, does="replace an existing agents.yml"))
    answers = (
        Exit(0, Lines(), "the starter config is written, the next step is printed, and so is the user library proposal"),
        Exit(1, STDERR, "the target is not a directory, or it already holds an agents.yml and --force was not given"),
    )
    carries = RunInit
    source = ("farrier/farrier/cli.py::_run_init", "farrier/farrier/init.py::default_config")


class Install(Command):
    does = "Render the selected skills and the launcher files into the repository."
    program = "farrier"
    argv = ("install", Flag("--repo", "repo"), Flag("--library", "library"))
    args = Object("InstallArgs", repo=REPO, library=LIBRARY)
    answers = (
        Exit(0, Lines(opaque=OPAQUE), "the generated files are written and their count is printed"),
        Exit(1, STDERR, "the library is not usable, or the repository has no agents.yml"),
    )
    carries = RunInstall
    source = ("farrier/farrier/cli.py::_run_install", "farrier/farrier/outputs.py::install_outputs", "farrier/farrier/install.py",
              "farrier/farrier/renderer.py", "farrier/farrier/sources.py", "farrier/farrier/manifest.py",
              "farrier/farrier/agents.py", "farrier/farrier/template_values.py", "farrier/farrier/selection_errors.py",
              "farrier/farrier/launcher.py", "farrier/farrier/managed_blocks.py", "farrier/farrier/link_rebase.py",
              "farrier/farrier/naming.py", "farrier/farrier/ownership.py")


class Scaffold(Command):
    does = "Seed repository files from a library scaffold definition, or list the scaffolds the repository may apply."
    program = "farrier"
    argv = ("scaffold", Positional("name"), Flag("--param", "dir", fmt="dir={}"), Flag("--repo", "repo"),
            Flag("--library", "library"))
    args = Object(
        "ScaffoldArgs",
        name=Field(Str(classes={"a scaffold the library does not define": "nonesuch"}), required=False,
                 does="the scaffold to apply; left out, the scaffolds available are listed"),
        dir=Field(Str(classes={"a folder name with a space": "my api"}), required=False, does="the folder the scaffold writes into, its dir parameter"),
        repo=Field(Str(classes={"a directory that does not exist": "elsewhere"}), required=False,
                   does="the repository root; the working directory when left out"),
        library=LIBRARY,
    )
    answers = (
        Exit(0, Lines(), "the files are created or kept and their count is printed, or the scaffolds are listed"),
        Exit(1, STDERR, "the library is not usable, or the scaffold is unknown or not enabled for the repository"),
    )
    carries = RunScaffold
    source = ("farrier/farrier/cli.py::_run_scaffold", "farrier/farrier/scaffolds.py")


def text(does: str, **classes: str) -> Field:
    return Field(Str(classes={label.replace("_", " "): value for label, value in classes.items()}), required=False, does=does)


class Version(Command):
    does = "Print the installed farrier version."
    program = "farrier"
    argv = ("version",)
    args = Object("VersionArgs")
    answers = (Exit(0, Lines(opaque=("",)), "the version number, which changes with each release"),)
    carries = act.RunVersion
    source = (f"{CLI}::_main",)


class Doctor(Command):
    does = "Report what a workflow will be unable to do with this repository's agents.yml."
    program = "farrier"
    argv = ("doctor", Flag("--repo", "repo"))
    args = Object("DoctorArgs", repo=REPO)
    answers = (
        Exit(0, Lines(), "the warnings, then the count of errors and warnings"),
        Exit(1, Lines(), "there is no agents.yml to read, and the report says so and counts the error"),
    )
    carries = act.RunDoctor
    source = (f"{CLI}::_main", "farrier/farrier/doctor.py")


class ConfigShow(Command):
    does = "Print every key the home config sets as key=value, or the bare value of one key."
    program = "farrier"
    argv = ("config", "show", Positional("key"))
    args = Object("ConfigShowArgs", key=text("the key to print; left out, every key set", a_key_the_file_does_not_set="nonesuch"))
    answers = (
        Exit(0, Lines(), "the keys in the order the schema lists them, or one value"),
        Exit(1, STDERR, "the key is not set in the file"),
    )
    carries = act.RunConfigShow
    source = (f"{CLI}::_dispatch_config", f"{CLI}::_run_config")


class ConfigGet(Command):
    does = "Print the value a key takes on this machine, its default when the file does not set it."
    program = "farrier"
    argv = ("config", "get", Positional("key"))
    args = Object("ConfigGetArgs", key=text("the dotted key", a_key_the_machine_config_lacks="nonesuch"))
    answers = (
        Exit(0, Lines(), "the value, or the default"),
        Exit(1, STDERR, "the key is not a machine-config key, or it is not set and has no default"),
    )
    carries = act.RunConfigGet
    source = (f"{CLI}::_dispatch_config", f"{CLI}::_config_value_text", "farrier/farrier/config_reference.py::home_key_type")


class ConfigSet(Command):
    does = "Write one key of the home config as KEY=VALUE, checked against the schema first."
    program = "farrier"
    argv = ("config", "set", Positional("assignment"))
    args = Object("ConfigSetArgs", assignment=text(
        "KEY=VALUE; a string key takes the value as typed", a_name_with_no_equals_sign="bogus", a_key_the_machine_config_lacks="bogus=1"))
    answers = (
        Exit(0, Lines(), "the assignment is written and echoed"),
        Exit(1, STDERR, "the text has no equals sign, or the key is not a machine-config key"),
    )
    carries = act.RunConfigSet
    source = (f"{CLI}::_dispatch_config", "farrier/farrier/config_reference.py::parse_home_value")


class ConfigReference(Command):
    does = "Describe the keys of the shared config files, or the one key named."
    program = "farrier"
    argv = ("config", "reference", Positional("key"))
    args = Object("ConfigReferenceArgs", key=text("the key to describe", a_key_no_config_file_has="nonesuch"))
    answers = (
        Exit(0, Lines(opaque=("",)), "the entry, whose text is the library's documentation of the key"),
        Exit(1, STDERR, "no config key matches"),
    )
    carries = act.RunConfigReference
    source = (f"{CLI}::_dispatch_config", "farrier/farrier/config_reference.py::reference_text")


class ConfigSetWorktree(Command):
    does = "Record the directory new git worktrees are cut into."
    program = "farrier"
    argv = ("config", "set-worktree", Positional("path"))
    args = Object("WorktreeDirArgs", path=text("the parent directory for worktrees"))
    answers = (Exit(0, Lines(), "the key and the absolute path, as written"),)
    carries = act.RunSetWorktree
    source = (f"{CLI}::_dispatch_config",)


class ConfigSetStablemate(Command):
    does = "Record the stablemate checkout path in the home config."
    program = "farrier"
    argv = ("config", "set-stablemate", Positional("path"))
    args = Object("StablemateDirArgs", path=text("the stablemate checkout"))
    answers = (Exit(0, Lines(), "the key and the absolute path, as written"),)
    carries = act.RunSetStablemate
    source = (f"{CLI}::_dispatch_config",)


class ConfigSetLibrary(Command):
    does = "Record the library directory in the home config."
    program = "farrier"
    argv = ("config", "set-library", Positional("path"))
    args = Object("LibraryDirArgs", path=text("the library directory", a_directory_with_no_library="nolib"))
    answers = (
        Exit(0, Lines(), "the key and the absolute path, as written"),
        Exit(1, STDERR, "the directory holds no library/"),
    )
    carries = act.RunSetLibrary
    source = (f"{CLI}::_dispatch_config", "farrier/farrier/layers.py::is_library_dir")


class ConfigSetBase(Command):
    does = "Record the base library content path in the home config."
    program = "farrier"
    argv = ("config", "set-base", Positional("path"))
    args = Object("BaseDirArgs", path=text("the base library directory", a_directory_with_no_library="nolib"))
    answers = (
        Exit(0, Lines(), "the key and the absolute path, as written"),
        Exit(1, STDERR, "the directory holds no library/"),
    )
    carries = act.RunSetBase
    source = (f"{CLI}::_dispatch_config",)


class LibraryList(Command):
    does = "List the library the layer stack resolves, one block per kind, each item with its layer."
    program = "farrier"
    argv = ("library", "list", Flag("--library", "library"))
    args = Object("LibraryListArgs", library=LIBRARY)
    answers = (
        Exit(0, Lines(), "the layers, then each kind with its items"),
        Exit(1, STDERR, "the library is not usable"),
    )
    carries = act.RunLibraryList
    source = (f"{CLI}::_run_library", f"{CLI}::_run_library_list", "farrier/farrier/library_view.py")


class LibraryShow(Command):
    does = "Print one library item's source as written."
    program = "farrier"
    argv = ("library", "show", Flag("--skill", "skill"), Flag("--library", "library"))
    args = Object("LibraryShowArgs", skill=text("the skill to print", a_skill_the_library_lacks="nonesuch"), library=LIBRARY)
    answers = (
        Exit(0, Lines(), "the file, line for line"),
        Exit(1, STDERR, "the library is not usable, no kind was named, or the library lacks the item"),
    )
    carries = act.RunLibraryShow
    source = (f"{CLI}::_run_library", f"{CLI}::_run_library_show", "farrier/farrier/library_view.py::find")


class LibraryCheck(Command):
    does = "Report front-matter problems in the library's sources."
    program = "farrier"
    argv = ("library", "check", Flag("--library", "library"))
    args = Object("LibraryCheckArgs", library=LIBRARY)
    answers = (
        Exit(0, Lines(), "the layers, then the count of sources that parse"),
        Exit(1, STDERR, "the library is not usable"),
    )
    carries = act.RunLibraryCheck
    source = (f"{CLI}::_run_library", f"{CLI}::_run_library_check", "farrier/farrier/library_check.py")


class Source(Command):
    does = "Print the editable library source of a generated skill."
    program = "farrier"
    argv = ("source", Positional("file"), Flag("--library", "library"))
    args = Object("SourceArgs", file=text("the generated file", a_file_farrier_did_not_write="agents.yml",
                                          a_file_that_is_not_there="nonesuch"), library=LIBRARY)
    answers = (
        Exit(0, Lines(), "the path of the library file the generated one came from"),
        Exit(1, STDERR, "the file is missing, the library is not usable, or farrier did not generate the file"),
    )
    carries = act.RunSource
    source = (f"{CLI}::_run_source", f"{CLI}::mapped_instruction_sources", "farrier/farrier/frontmatter.py",
              "farrier/farrier/local_instructions.py", "farrier/farrier/layers.py")


class Eject(Command):
    does = "Hand a generated skill over to the repository, and render again without it."
    program = "farrier"
    argv = ("eject", Positional("name"), Flag("--library", "library"))
    args = Object("EjectArgs", name=text("the installed skill's folder name", a_skill_the_repo_does_not_generate="demo"), library=LIBRARY)
    answers = (
        Exit(0, Lines(), "the skill is released, agents.yml stops selecting it, and the install runs again"),
        Exit(1, STDERR, "the library is not usable, the repository has no agents.yml, or the name is not ejectable"),
    )
    carries = act.RunEject
    source = (f"{CLI}::_run_eject", "farrier/farrier/eject.py", "farrier/farrier/yaml_edit.py")


class HooksList(Command):
    does = "List the hooks the selected skills declare, by stage."
    program = "farrier"
    argv = ("hooks", "list", Flag("--repo", "repo"))
    args = Object("HooksListArgs", repo=REPO)
    answers = (
        Exit(0, Lines(), "the hooks by stage, or that no library is available"),
        Exit(1, STDERR, "the repository has no agents.yml"),
    )
    carries = act.RunHooksList
    source = (f"{CLI}::_run_hooks_list", "farrier/farrier/skill_hooks.py")


class HooksInstall(Command):
    does = "Wire this repository's git hooks through the manager agents.yml names."
    program = "farrier"
    argv = ("hooks", "install", Switch("--dry-run", "dry_run"))
    args = Object("HooksInstallArgs", dry_run=Field(Bool(), required=False, does="print every action with no writes"))
    answers = (Exit(0, Lines(opaque=("Wired ", "[dry-run] Wired ")), "the hooks are wired, or each action is announced, and the manager is named"),)
    carries = act.RunHooksInstall
    source = (f"{CLI}::_run_hooks_install", "farrier/farrier/hook_managers.py")


class Checks(Command):
    does = "List the commit checks an agent's commit runs in this repository, with their budgets."
    program = "farrier"
    argv = ("checks",)
    args = Object("ChecksArgs")
    answers = (Exit(0, Lines(opaque=("/",)), "one line per check; none when no library resolves"),)
    carries = act.RunChecks
    source = (f"{CLI}::_run_checks", "farrier/farrier/sync.py::sync_command")


class Sync(Command):
    does = "Reinstall drifted generated files and stage them, as an agent commit check."
    program = "farrier"
    argv = ("sync",)
    args = Object("SyncArgs")
    answers = (Exit(0, Lines(), "nothing, whether the files are current or the library cannot be resolved"),)
    carries = act.RunSync
    source = (f"{CLI}::_run_sync", "farrier/farrier/sync.py::sync", "farrier/farrier/drift.py")


class InstallUser(Command):
    does = "Render the user library into the harness home directories."
    program = "farrier"
    argv = ("install", "--user", Flag("--library", "library"), Flag("--home", "home"))
    args = Object("InstallUserArgs", library=LIBRARY, home=text("the home directory to install into"))
    answers = (
        Exit(0, Lines(), "the generated files are written into the home and counted"),
        Exit(1, STDERR, "the library is not usable, or the home config has no user library table"),
    )
    carries = act.RunInstallUser
    source = (f"{CLI}::_run_user_install", "farrier/farrier/home_agents.py", "farrier/farrier/home_entries.py",
              "farrier/farrier/home_guards.py", "farrier/farrier/user_library.py")


class Workflows(Command):
    does = "List the workflows installed on this machine through pipx."
    program = "farrier"
    argv = ("workflows",)
    args = Object("WorkflowsArgs")
    answers = (Exit(0, Lines(), "the distributions and their workflows, or that none is installed"),)
    carries = act.RunWorkflows
    source = (f"{CLI}::_run_workflows", "farrier/farrier/pipx.py")


class WorkflowNames(Command):
    does = "Print just the names of the installed workflows, on one line."
    program = "farrier"
    argv = ("workflows", "--names")
    args = Object("WorkflowNamesArgs")
    answers = (Exit(0, Lines(), "the names separated by spaces, an empty line when none"),)
    carries = act.RunWorkflowNames
    source = (f"{CLI}::_run_workflows",)


class Worktrees(Command):
    does = "List the linked worktrees that are safe to remove."
    program = "farrier"
    argv = ("worktrees",)
    args = Object("WorktreesArgs")
    answers = (Exit(0, Lines(), "one row per worktree; nothing in a folder that holds no git checkout"),)
    carries = act.RunWorktrees
    source = (f"{CLI}::_run_worktrees", "farrier/farrier/worktree_sweep.py")


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("farrier/farrier/outputs.py::install_outputs",)


ALL = (Init, Install, Scaffold, Version, Doctor, ConfigShow, ConfigGet, ConfigSet, ConfigReference, ConfigSetWorktree,
       ConfigSetStablemate, ConfigSetLibrary, ConfigSetBase, LibraryList, LibraryShow, LibraryCheck, Source, Eject,
       HooksList, HooksInstall, Checks, Sync, InstallUser, Workflows, WorkflowNames, Worktrees, Look)
