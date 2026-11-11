"""The farrier commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Files, Flag, Lines, Object, Positional, Str, Switch

from .model.actions import ListFiles, RunInit, RunInstall, RunScaffold
from .model.files import MARKS

OPAQUE = ("Updated .agents", "Wired ", "Added agent launcher")

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
    source = ("farrier/farrier/cli.py::_run_install", "farrier/farrier/outputs.py::install_outputs")


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
    source = ("farrier/farrier/cli.py::_run_scaffold",)


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("farrier/farrier/outputs.py::install_outputs",)


ALL = (Init, Install, Scaffold, Look)
