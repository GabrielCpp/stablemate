"""The workflows commands the book plays: what a person types, and every way each one can end."""

from __future__ import annotations

from ostler.book import STDERR, Bool, Command, Exit, Field, Files, Flag, Int, Lines, Object, Positional, Str, Switch

from .model.actions import (ListFiles, RunAuthor, RunCoder, RunLoopRunner, RunNew, RunNewProgram, RunOkfBook,
                            RunResearch, RunReviewDebt)
from .model.files import MARKS
from .sources import AUTHOR, CODER, KIT, LOOP_RUNNER, NEW, OKF_BOOK, PROGRAM, RESEARCH, REVIEW_DEBT

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
        into=Field(Str(classes={"a folder name": "elsewhere", "a nested folder": "deep/elsewhere"}), required=False, does="the directory to create the workflow in; the working directory when left out"),
    )
    answers = (
        Exit(0, Lines(), "the distribution is written under the name and the next steps are printed"),
        Exit(1, STDERR, "the name is not kebab-case, the check is blank, or the target already exists"),
        Exit(2, STDERR, "the name or --check is missing, and the usage is printed"),
    )
    carries = RunNew
    source = ("workflows/src/workhorse_workflows/new/scaffold.py::main",
              "workflows/src/workhorse_workflows/new/scaffold.py::scaffold", *NEW)


class NewProgram(Command):
    does = "Write the folder of a research program: its manifest, README, progress log and first gate."
    program = "python"
    argv = ("-m", "workhorse_workflows.research.scaffold.new_program", Flag("--dir", "dir"),
            Flag("--code-root", "code_root"), Flag("--gate", "gate"), Switch("--set-default", "set_default"),
            Switch("--force", "force"))
    args = Object(
        "NewProgramArgs",
        dir=Field(Str(classes={"a folder with a slash after it": "specs/demo/", "a folder with two slashes after it": "specs/demo//"}), required=False, ignores=("case", "surrounding spaces"),
                  why="the folder name is a path, and a path spelled another way is another folder.",
                  does="the program folder, relative to the working directory"),
        code_root=Field(Str(classes={"a source folder": "src/app", "a top level source folder": "lib"}), required=False, ignores=("case", "surrounding spaces"),
                        why="the source folder is named in the README as typed, and another spelling is another folder.",
                        does="the source folder the program's experiments live in"),
        gate=Field(Str(classes={"a gate id": "G1", "a lowercase gate id": "g2"}), required=False, ignores=("case", "surrounding spaces"),
                   why="the gate id names the first gate's file and heading as typed.",
                   does="the id of the first gate; G0 when left out"),
        set_default=Field(Bool(), required=False, does="point .agents/program at this program"),
        force=Field(Bool(), required=False, does="overwrite the files a program folder already holds"),
    )
    answers = (
        Exit(0, Lines(opaque=("  created ",)), "each file written is named, and the program's findings folder when it is new"),
        Exit(1, STDERR, "the program's manifest is already there and --force was not given"),
        Exit(2, STDERR, "the folder or the source folder is missing, and the usage is printed"),
    )
    carries = RunNewProgram
    source = ("workflows/src/workhorse_workflows/research/scaffold/new_program.py::main", *PROGRAM)


class DryRunLoopRunner(Command):
    does = "Check the loop-runner workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-loop-runner"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunLoopRunner
    source = ("workflows/src/workhorse_workflows/loop_runner/workflow.py::main", *LOOP_RUNNER, *KIT, ENTRY, ENGINE)


class DryRunResearch(Command):
    does = "Check the research workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-research"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunResearch
    source = ("workflows/src/workhorse_workflows/research/workflow.py::main", *RESEARCH, *KIT, ENTRY, ENGINE)


class DryRunAuthor(Command):
    does = "Check the author workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-author"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunAuthor
    source = ("workflows/src/workhorse_workflows/author/workflow.py::main", *AUTHOR, *KIT, ENTRY, ENGINE)


class DryRunCoder(Command):
    does = "Check the coder workflow loads and every state is reachable, with the agent stubbed. A turn_minutes that is not above zero is refused before any turn starts."
    program = "workhorse-coder"
    argv = ("run", "--dry-run", Flag("--params", "turn_minutes", fmt='{{"turn_minutes": {}}}'))
    args = Object(
        "CoderArgs",
        turn_minutes=Field(Int(), required=False, does="the minutes one owner turn or resolver turn may run before the run cuts it"),
    )
    answers = (
        Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),
        Exit(1, Lines(opaque=("    For further information",)), "turn_minutes is not above zero, and the launch names it"),
    )
    carries = RunCoder
    source = ("workflows/src/workhorse_workflows/coder/main/flow.py::Coder", "workflows/src/workhorse_workflows/coder/workflow.py::main", *CODER, *KIT, ENTRY, ENGINE)


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
    source = ("workflows/src/workhorse_workflows/okf_book/workflow.py::main", *OKF_BOOK, *KIT, ENTRY, ENGINE,
              "workhorse/workhorse/references.py::missing_references")


class DryRunReviewDebt(Command):
    does = "Check the review-debt workflow loads and every state is reachable, with the agent stubbed."
    program = "workhorse-review-debt"
    argv = ("run", "--dry-run")
    args = NONE
    answers = (Exit(0, Lines(), "the run name and the directory holding its artifacts are printed"),)
    carries = RunReviewDebt
    source = ("workflows/src/workhorse_workflows/review_debt/workflow.py::main", *REVIEW_DEBT, *KIT, ENTRY, ENGINE)


class Look(Files):
    does = "List the watched files of the sandbox with the strings each holds."
    marks = MARKS
    carries = ListFiles
    source = ("workflows/src/workhorse_workflows/new/scaffold.py::scaffold", ENGINE)


ALL = (New, NewProgram, DryRunLoopRunner, DryRunResearch, DryRunAuthor, DryRunCoder, DryRunOkfBook, DryRunReviewDebt, Look)
