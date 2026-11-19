"""The book's own commands as nodes, which both flows judge a book by: check, run and missing."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict
from workhorse_workflows.kit.book_files import BOOK_ENV, book_command
from workhorse_workflows.kit.tools import run_tool
from workhorse_workflows.okf_book.shared.blueprint import blueprint

UNNAMED_HEADING = "## Files no element names"
GATE_TAIL_LINES = 200
GATE_LINE_CHARS = 2000
PROGRESS_TAIL_LINES = 20


class BookGate(BaseModel):
    """What one of the book's own commands said: its exit code and the tail of its output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    output: str = ""


class MissingList(BookGate):
    """What the book's missing said, with the files no element names."""

    unnamed: tuple[str, ...] = ()


def _green(_logger: logging.Logger, *_args: object) -> BookGate:
    return BookGate(exit_code=0, output="dry run")


def _missing_green(_logger: logging.Logger, *_args: object) -> MissingList:
    return MissingList(exit_code=0, output="dry run")


def _narrow(line: str) -> str:
    if len(line) <= GATE_LINE_CHARS:
        return line
    return f"{line[:GATE_LINE_CHARS]} … [{len(line) - GATE_LINE_CHARS} more characters cut]"


def tail(text: str) -> str:
    return "\n".join(_narrow(line) for line in text.splitlines()[-GATE_TAIL_LINES:])


def _unnamed(stdout: str) -> tuple[str, ...]:
    found: list[str] = []
    inside = False
    for line in stdout.splitlines():
        if line == UNNAMED_HEADING:
            inside = True
        elif line.startswith("## "):
            inside = False
        elif inside and line.startswith("- "):
            found.append(line[2:])
    return tuple(found)


@blueprint.node(stub=_green)
def python_book_check(logger: logging.Logger, root: Path, module: str, app: Path) -> BookGate:
    """Run the check of one of the book's modules from the book root, with the source pointers read under the app's root, and keep the tail of what it printed."""
    done = run_tool(book_command("check", module, "--app", str(app)), cwd=root, logger=logger, env=BOOK_ENV)
    return BookGate(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()))


@blueprint.node(stub=_missing_green)
def python_book_missing(logger: logging.Logger, root: Path, module: str, app: Path, under: str) -> MissingList:
    """List the tracked source files of the app, under the folder the run names, that no element of one of the book's modules names, and keep the tail of what it printed."""
    where = ("--under", under) if under else ()
    done = run_tool(book_command("missing", module, "--app", str(app), *where), cwd=root, logger=logger, env=BOOK_ENV)
    return MissingList(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()), unnamed=_unnamed(done.stdout))


def run_flags(stack_copy: str = "", only: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The flags a run takes to play only the journeys of the named calls, on the named stack copy."""
    return (*(("--only", ",".join(only)) if only else ()), *(("--copy", stack_copy) if stack_copy else ()))


@blueprint.node(stub=_green)
def python_book_run(logger: logging.Logger, root: Path, module: str, out_dir: Path, flags: tuple[str, ...] = ()) -> BookGate:
    """Play one of the book's modules against the live app from the book root, with the flags the run names, and keep the last lines of its progress and the tail of its report."""
    done = run_tool([*book_command("run", module, "--out", str(out_dir)), *flags], cwd=root, logger=logger, env=BOOK_ENV)
    progress = "\n".join(_narrow(line) for line in done.stderr.splitlines()[-PROGRESS_TAIL_LINES:])
    return BookGate(exit_code=done.returncode, output=f"{progress}\n\n{tail(done.stdout)}".strip())


@blueprint.node(stub=_green)
def python_book_verified(logger: logging.Logger, root: Path, module: str, app: Path) -> BookGate:
    """Stamp the app's HEAD as the commit one of the book's modules is verified at, which the book refuses while a changed file or function is named by no element."""
    done = run_tool(book_command("verified", module, "--app", str(app)), cwd=root, logger=logger, env=BOOK_ENV)
    return BookGate(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()))


def _no_calls(_logger: logging.Logger, *_args: object) -> list[str]:
    return ["Ping"]


CALLS_SCRIPT = (
    "import json, sys\n"
    "from ostler.book.cli import load\n"
    "service = load(sys.argv[1])\n"
    "print(json.dumps(sorted(e.__name__ for e in (*service.endpoints, *service.interactions))))\n"
)


@blueprint.node(stub=_no_calls)
def python_book_calls(logger: logging.Logger, root: Path, module: str) -> list[str]:
    """List the endpoints and interactions one of the book's modules declares, which the book's run takes by name."""
    done = run_tool([sys.executable, "-c", CALLS_SCRIPT, module], cwd=root, logger=logger, env=BOOK_ENV)
    if done.returncode != 0:
        logger.warning("listing the calls of %s exited %s: %s", module, done.returncode, done.stderr.strip())
        return []
    return cast("list[str]", json.loads(done.stdout))


class StaleSaid(BookGate):
    """What the book's stale said of one module: its exit code, its whole stdout and its stderr."""

    error: str = ""


def run_stale(logger: logging.Logger, root: Path, module: str, app: Path) -> StaleSaid:
    """What the book's stale said of one module, whole, since a cut report would hide an element."""
    done = run_tool(book_command("stale", module, "--app", str(app)), cwd=root, logger=logger, env=BOOK_ENV)
    return StaleSaid(exit_code=done.returncode, output=done.stdout, error=done.stderr)
