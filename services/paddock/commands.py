"""The paddock commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Files, Flag, Int, Lines, List, Object, Positional, Str, Switch

from .model import actions as act
from .model.files import MARKS

CLI = "paddock/paddock/cli.py"
OPAQUE = ("run     ", "result  ")

BENCHMARK = Field(Str(classes={"a benchmark the root does not hold": "nope"}), required=False,
                  does="the benchmark, a folder under gold/")
TASK = Field(Str(classes={"a task the benchmark does not declare": "nope"}), required=False,
             does="the task the benchmark's tasks.py declares")
UNPINNED = Field(Bool(), required=False, does="drive the checkout in place instead of a clone pinned at its HEAD")
QUIET = Field(Bool(), required=False, does="do not tee each command's output to stderr; stderr of a success is not compared")

LOADING = ("paddock/paddock/loader.py", "paddock/paddock/paths.py", "paddock/paddock/registry.py")
ROUND = ("paddock/paddock/runner.py", "paddock/paddock/names.py", "paddock/paddock/homeconfig.py",
         "paddock/paddock/project.py", "paddock/paddock/reap.py", "paddock/paddock/manifest.py")
HELPERS = ("paddock/paddock/tasks/inputs.py", "paddock/paddock/tasks/judge.py", "paddock/paddock/tasks/forensics.py",
           "paddock/paddock/tasks/operator_gates.py", "paddock/paddock/tasks/tree.py", "paddock/paddock/tasks/stablemate.py",
           "paddock/paddock/tasks/replay.py", "paddock/paddock/tasks/greenfield.py")


class ListBenchmarks(Command):
    does = "List every task of every benchmark under the root, one line each, and name the benchmarks that do not load."
    program = "paddock"
    argv = ("list",)
    args = Object("ListArgs")
    answers = (
        Exit(0, Lines(), "one line per task, or that the root holds no benchmarks"),
        Exit(1, Lines(), "the tasks of the benchmarks that load; a benchmark that does not load is named on stderr"),
        Exit(2, STDERR, "the home config does not parse"),
    )
    carries = act.ListBenchmarks
    source = (f"{CLI}::cmd_list", *LOADING)


class RunTask(Command):
    does = "Copy a benchmark's data, run a task's steps against the copy, score it when the task brought a ruler, and write the result."
    program = "paddock"
    argv = ("run", Positional("benchmark"), Positional("task"), Switch("--no-pin-project", "no_pin_project"), Switch("--quiet", "quiet"))
    args = Object("RunArgs", benchmark=BENCHMARK, task=TASK, no_pin_project=UNPINNED, quiet=QUIET)
    answers = (
        Exit(0, Lines(opaque=OPAQUE), "every step's outcome, then the score when the task has one"),
        Exit(1, STDERR, "no such benchmark or task, or the data is not a repository with a commit"),
        Exit(2, STDERR, "the home config does not parse"),
        Exit(130, None, "a step stopped the round, which `paddock resume` continues"),
    )
    carries = act.RunTask
    source = (f"{CLI}::cmd_run", f"{CLI}::_report", f"{CLI}::main", *LOADING, *ROUND, *HELPERS)


class RunTaskThatFails(Command):
    does = "Run a task one of whose steps fails: the outcome of each step is printed, the later steps are skipped, and the round exits 1."
    program = "paddock"
    argv = ("run", "acme", Positional("task"), Switch("--no-pin-project", "no_pin_project"), Switch("--quiet", "quiet"))
    args = Object(
        "RunStepArgs",
        task=Field(Str(classes={"a step raises": "failing", "a step reads a boolean as a number": "inputs",
                                "a step runs a command that is not installed": "tools"}), required=False,
                   does="the task the benchmark's tasks.py declares"),
        no_pin_project=UNPINNED,
        quiet=QUIET,
    )
    answers = (
        Exit(0, Lines(opaque=OPAQUE), "every step's outcome"),
        Exit(1, Lines(opaque=OPAQUE), "a step failed, its error is on its line, and the steps after it are skipped; a run refused before its first step prints nothing on stdout"),
        Exit(2, STDERR, "the home config does not parse"),
    )
    carries = act.RunTaskThatFails
    source = (f"{CLI}::cmd_run", f"{CLI}::_report", "paddock/paddock/runner.py::_run_steps", "paddock/paddock/runner.py::_run_step")


class ResumeTask(Command):
    does = "Continue an interrupted round on the stablemate commit it started on: the steps that have no ok outcome run, the others are kept."
    program = "paddock"
    argv = ("resume", Positional("benchmark"), Positional("task"), Positional("n"), Switch("--quiet", "quiet"))
    args = Object(
        "ResumeArgs",
        benchmark=BENCHMARK,
        task=TASK,
        n=Field(Int(), required=False, does="the round number; left out, the highest one without a result"),
        quiet=QUIET,
    )
    answers = (
        Exit(0, Lines(opaque=OPAQUE), "every step's outcome, the finished ones as the interrupted segment left them"),
        Exit(1, STDERR, "no such benchmark or task, no interrupted round to continue, or the round already has a result"),
        Exit(2, STDERR, "the home config does not parse"),
    )
    carries = act.ResumeTask
    source = (f"{CLI}::cmd_resume", "paddock/paddock/runner.py::resume", "paddock/paddock/runner.py::_unfinished_workspace",
              "paddock/paddock/runner.py::_interrupt", *LOADING)


class SandboxRun(Command):
    does = "Run a command in a container that sees the app and the run's folders and not the stablemate checkout."
    program = "paddock"
    argv = ("sandbox", "run", Flag("--app", "apps"), Flag("--workdir", "workdir"), Flag("--runs-dir", "runs_dir"),
            Flag("--config", "config"), Flag("--credentials", "credentials"), "--", Positional("command"))
    args = Object(
        "SandboxRunArgs",
        apps=Field(List(Str()), does="a repo the command works on, once per repo"),
        workdir=Field(Str(), required=False, does="the --app directory name the command starts in; needed with several --app"),
        runs_dir=Field(Str(), does="where the command writes its runs"),
        config=Field(Str(classes={"a config that is not there": "sbx/none.toml"}), does="the stablemate config the command reads"),
        credentials=Field(Str(), required=False, does="the Claude Code login, mounted when the config runs claude"),
        command=Field(Str(classes={"a command to run": "true"}), required=False, does="the command, after `--`"),
    )
    answers = (
        Exit(0, Lines(), "the command ran in the container and its exit code came back"),
        Exit(1, STDERR, "no command, an unreadable config, a login the sandbox lacks, a mount that is missing or that would show the checkout, or no --workdir for several apps"),
    )
    carries = act.SandboxRun
    source = (f"{CLI}::_add_sandbox_commands", f"{CLI}::cmd_sandbox_run", f"{CLI}::_logins", f"{CLI}::_command_after_separator",
              "paddock/paddock/sandbox.py")


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = act.ListFiles
    source = ("paddock/paddock/runner.py::_write_ledger",)


ALL = (ListBenchmarks, RunTask, RunTaskThatFails, ResumeTask, SandboxRun, Look)
