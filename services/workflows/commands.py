"""The workflows commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Command, Exit, Field, Files, Flag, Lines, Object, Positional, Str

from .model.actions import (ListFiles, RunAuthor, RunCoder, RunLoopRunner, RunNew, RunOkfBook, RunResearch,
                            RunReviewDebt)
from .model.files import MARKS

NONE = Object("DryRunArgs")
ENGINE = "workhorse/workhorse/pyflow/run.py::run_pyflow"
ENTRY = "workhorse/workhorse/cli/__init__.py::console_script"


class New(Command):
    does = "Write a standalone workflow distribution that loops an agent until a check command exits 0."
    program = "workhorse-new"
    argv = (Positional("name"), Flag("--check", "check"), Flag("--into", "into"))
    args = Object(
        "NewArgs",
        name=Field(
            Str(classes={"a name with capital letters": "Fix-Tests", "a name that starts with a digit": "1fix",
                         "a name with a double dash": "fix--tests"}),
            required=False, does="the workflow name; the command becomes workhorse-NAME"),
        check=Field(Str(classes={"a blank command": "  "}), required=False,
                    does="the shell command that decides when the work is done"),
        into=Field(Str(), required=False, does="the directory to create the workflow in; the working directory when left out"),
    )
    answers = (
        Exit(0, Lines(), "the distribution is written under the name and the next steps are printed"),
        Exit(1, STDERR, "the name is not kebab-case, the check is blank, or the target already exists"),
        Exit(2, STDERR, "the name or --check is missing, and the usage is printed"),
    )
    carries = RunNew
    source = ("workflows/src/workhorse_workflows/new/scaffold.py::main",
              "workflows/src/workhorse_workflows/new/scaffold.py::scaffold")


class DryRunLoopRunner(Command):
    does = "Check the loop-runner workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-loop-runner"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunLoopRunner
    source = ("workflows/src/workhorse_workflows/loop_runner/workflow.py::main", ENTRY, ENGINE)


class DryRunResearch(Command):
    does = "Check the research workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-research"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunResearch
    source = ("workflows/src/workhorse_workflows/research/workflow.py::main", ENTRY, ENGINE)


class DryRunAuthor(Command):
    does = "Check the author workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-author"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunAuthor
    source = ("workflows/src/workhorse_workflows/author/workflow.py::main", ENTRY, ENGINE)


class DryRunCoder(Command):
    does = "Check the coder workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-coder"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (
        Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),
        Exit(1, Lines(), "a skill its prompts name is installed neither in the repository nor at home"),
    )
    carries = RunCoder
    source = ("workflows/src/workhorse_workflows/coder/workflow.py::main", ENTRY, ENGINE,
              "workhorse/workhorse/references.py::missing_references")


class DryRunOkfBook(Command):
    does = "Check the okf-book workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-okf-book"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (
        Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),
        Exit(1, Lines(), "a skill its prompts name is installed neither in the repository nor at home"),
    )
    carries = RunOkfBook
    source = ("workflows/src/workhorse_workflows/okf_book/workflow.py::main", ENTRY, ENGINE,
              "workhorse/workhorse/references.py::missing_references")


class DryRunReviewDebt(Command):
    does = "Check the review-debt workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-review-debt"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunReviewDebt
    source = ("workflows/src/workhorse_workflows/review_debt/workflow.py::main", ENTRY, ENGINE)


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("workflows/src/workhorse_workflows/new/scaffold.py::scaffold", ENGINE)


ALL = (New, DryRunLoopRunner, DryRunResearch, DryRunAuthor, DryRunCoder, DryRunOkfBook, DryRunReviewDebt, Look)
