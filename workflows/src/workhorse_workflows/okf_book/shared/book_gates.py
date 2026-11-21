"""The book's own commands as nodes, which both flows judge a book by: check, run and missing."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import cast

from pydantic import BaseModel, ConfigDict
from workhorse_workflows.kit.book_files import BOOK_ENV, book_command
from workhorse_workflows.kit.git import head_sha
from workhorse_workflows.kit.tools import run_tool
from workhorse_workflows.okf_book.shared.blueprint import blueprint

UNNAMED_HEADING = "## Files no element names"
GATE_TAIL_LINES = 200
GATE_LINE_CHARS = 2000
PROGRESS_TAIL_LINES = 20
AFFECTED_PLANNED = (0, 1)
PLAY_TIMEOUT_EXIT = 3
NOTE_LINE = "NOTE "


class BookGate(BaseModel):
    """What one of the book's own commands said: its exit code and the tail of its output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    exit_code: int
    output: str = ""


class MissingList(BookGate):
    """What the book's missing said, with the files no element names."""

    unnamed: tuple[str, ...] = ()


class CheckSaid(BookGate):
    """What the book's check said: its exit code, the tail of its output, and every note it printed, whole."""

    noted: tuple[str, ...] = ()


def _green(_logger: logging.Logger, *_args: object) -> BookGate:
    return BookGate(exit_code=0, output="dry run")


def _check_green(_logger: logging.Logger, *_args: object) -> CheckSaid:
    return CheckSaid(exit_code=0, output="dry run")


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


def note_lines(text: str) -> tuple[str, ...]:
    """The notes a check printed, each as `<element>: <problem>`, whole however many there are."""
    return tuple(_narrow(line[len(NOTE_LINE):].strip()) for line in text.splitlines() if line.startswith(NOTE_LINE))


@blueprint.node(stub=_check_green)
def python_book_check(logger: logging.Logger, root: Path, module: str, app: Path) -> CheckSaid:
    """Run the check of one of the book's modules from the book root, with the source pointers read under the app's root, and keep the tail of what it printed and every note it printed."""
    done = run_tool(book_command("check", module, "--app", str(app)), cwd=root, logger=logger, env=BOOK_ENV)
    return CheckSaid(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()), noted=note_lines(done.stdout))


@blueprint.node(stub=_missing_green)
def python_book_missing(logger: logging.Logger, root: Path, module: str, app: Path, under: str) -> MissingList:
    """List the tracked source files of the app, under the folder the run names, that no element of one of the book's modules names, and keep the tail of what it printed."""
    where = ("--under", under) if under else ()
    done = run_tool(book_command("missing", module, "--app", str(app), *where), cwd=root, logger=logger, env=BOOK_ENV)
    return MissingList(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()), unnamed=_unnamed(done.stdout))


def run_flags(stack_copy: str = "", only: tuple[str, ...] = (), fresh: bool = False, journeys: tuple[str, ...] = ()) -> tuple[str, ...]:
    """The flags a run takes to play only the journeys of the named calls, or only the journeys of the named titles as a partial run, on the named stack copy, after the data is reloaded when `fresh`."""
    titled = ("--partial", *(flag for title in journeys for flag in ("--journey", title))) if journeys else ()
    return (*(("--only", ",".join(only)) if only else ()), *titled, *(("--copy", stack_copy) if stack_copy else ()), *(("--fresh-data",) if fresh else ()))


def _played(done: subprocess.CompletedProcess[str]) -> BookGate:
    progress = "\n".join(_narrow(line) for line in done.stderr.splitlines()[-PROGRESS_TAIL_LINES:])
    return BookGate(exit_code=done.returncode, output=f"{progress}\n\n{tail(done.stdout)}".strip())


@blueprint.node(stub=_green)
def python_book_run(logger: logging.Logger, root: Path, module: str, out_dir: Path, flags: tuple[str, ...] = ()) -> BookGate:
    """Play one of the book's modules against the live app from the book root, with the flags the run names, and keep the last lines of its progress and the tail of its report."""
    return _played(run_tool([*book_command("run", module, "--out", str(out_dir)), *flags], cwd=root, logger=logger, env=BOOK_ENV))


class PlayLimit(BaseModel):
    """The flags of a play and how many minutes it may take."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    flags: tuple[str, ...] = ()
    minutes: int


def _printed(text: str | bytes | None) -> str:
    return text.decode("utf-8", "replace") if isinstance(text, bytes) else text or ""


@blueprint.node(stub=_green)
def python_book_play(logger: logging.Logger, root: Path, module: str, out_dir: Path, limit: PlayLimit) -> BookGate:
    """Play one of the book's modules as `python_book_run` does, and stop a play still running after the limit's minutes. That play exits 3, as a play the environment could not judge, and says it did not end within the limit. No limit when the minutes are 0."""
    argv = [*book_command("run", module, "--out", str(out_dir)), *limit.flags]
    try:
        done = run_tool(argv, cwd=root, logger=logger, env=BOOK_ENV, timeout=limit.minutes * 60.0 if limit.minutes > 0 else None)
    except subprocess.TimeoutExpired as expired:
        printed = tail(f"{_printed(expired.stdout)}\n{_printed(expired.stderr)}".strip())
        return BookGate(exit_code=PLAY_TIMEOUT_EXIT, output=f"the play did not end within {limit.minutes} minutes (play_minutes)\n{printed}".strip())
    return _played(done)


@blueprint.node(stub=_green)
def python_book_verified(logger: logging.Logger, root: Path, module: str, app: Path) -> BookGate:
    """Stamp the app's HEAD as the commit one of the book's modules is verified at, which the book refuses while a changed file or function is named by no element."""
    done = run_tool(book_command("verified", module, "--app", str(app)), cwd=root, logger=logger, env=BOOK_ENV)
    return BookGate(exit_code=done.returncode, output=tail(f"{done.stdout}\n{done.stderr}".strip()))


class Selection(BookGate):
    """What the book's affected selected to play: the plan, the calls for `--only`, the journey titles for `--partial --journey`, and for a whole plan the reason it is whole."""

    plan: str = ""
    only: tuple[str, ...] = ()
    journeys: tuple[str, ...] = ()
    whole: bool = False
    reason: str = ""


def _nothing_selected(_logger: logging.Logger, *_args: object) -> Selection:
    return Selection(exit_code=0, output="dry run", plan="none")


@blueprint.node(stub=_nothing_selected)
def python_book_affected(logger: logging.Logger, root: Path, module: str, app: Path, out_dir: Path) -> Selection:
    """Read the plays the uncommitted edits of one of the book's modules call for, from the app's HEAD so that the diff is the working tree alone, and keep the plan `affected` wrote to the output folder."""
    base = head_sha(app)
    if not base:
        return Selection(exit_code=2, output=f"the HEAD of {app} could not be read")
    done = run_tool(book_command("affected", module, "--app", str(app), "--since", base, "--out", str(out_dir)), cwd=root, logger=logger, env=BOOK_ENV)
    said = tail(f"{done.stdout}\n{done.stderr}".strip())
    written = sorted(out_dir.glob("*-affected.json")) if done.returncode in AFFECTED_PLANNED else []
    if not written:
        return Selection(exit_code=done.returncode, output=said)
    plan = cast("dict[str, object]", json.loads(written[0].read_text(encoding="utf-8")))
    return Selection(
        exit_code=done.returncode,
        output=said,
        plan=str(plan.get("plan", "")),
        only=tuple(cast("list[str]", plan.get("only", []))),
        journeys=tuple(cast("list[str]", plan.get("by_journey", []))),
        whole=bool(plan.get("whole", False)),
        reason=str(plan.get("reason", "")),
    )


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
