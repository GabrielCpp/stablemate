"""The work of a writer's check or scenario run, kept apart from the call that starts it, so a call its shell hands back early leaves a result the same command reads on its next call."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from pydantic import TypeAdapter

from workhorse_workflows.okf_book.main.nodes.writer_commands import (
    CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,
    CommandOutput,
    printed_lines,
    read_command_state,
    spend_check_or_scenario_run,
)
from workhorse_workflows.okf_book.main.nodes.writer_stack import KeptStack

JOBS_FOLDER = "writer-jobs"
ATTACH_WAIT_S = 25.0
POLL_S = 0.5
SETTLE_WAIT_S = 1800.0
STILL_RUNNING_LINE = (
    "still running: run this same command again to read its result. Each call waits up to 25 seconds for it, and spends no run. "
    "Keep fixing meanwhile: an edit you make now is not in this result"
)
STOPPED_LINE = "the run stopped before it printed its result: run the command again"
_PID = "pid"
_RESULT = "result.json"
_DELIVERED = "delivered"
_OUTPUT = TypeAdapter(CommandOutput)

type Work = Callable[[Sequence[str]], CommandOutput]
type Start = Callable[[Path, Sequence[str]], None]


def jobs_folder(run_dir: Path) -> Path:
    """Where the jobs of the writer's commands are."""
    return run_dir / JOBS_FOLDER


def job_folder(name: str, argv: Sequence[str]) -> Path:
    """The job of the command `name` run with `argv`, whose first argument is the command state file."""
    key = hashlib.sha256(json.dumps([name, *argv]).encode()).hexdigest()[:16]
    return jobs_folder(Path(argv[0]).parent) / key


def book_digest(root: Path) -> str:
    """What changes whenever a page under the repository's `docs/` is written."""
    digest = hashlib.sha256()
    for path in sorted((root / "docs").rglob("*.md")):
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(f"{path}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode())
    return digest.hexdigest()


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        return Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return True


def _result(job: Path) -> CommandOutput | None:
    path = job / _RESULT
    return _OUTPUT.validate_json(path.read_text(encoding="utf-8")) if path.is_file() else None


def _running(job: Path) -> bool:
    pid = job / _PID
    return pid.is_file() and not (job / _RESULT).is_file() and _alive(int(pid.read_text(encoding="utf-8")))


def _root(argv: Sequence[str]) -> Path:
    return read_command_state(Path(argv[0])).root.resolve()


def _unread_or_unchanged(job: Path, argv: Sequence[str]) -> bool:
    delivered = job / _DELIVERED
    return not delivered.is_file() or delivered.read_text(encoding="utf-8") == book_digest(_root(argv))


def _deliver(job: Path, argv: Sequence[str], result: CommandOutput) -> CommandOutput:
    _ = (job / _DELIVERED).write_text(book_digest(_root(argv)), encoding="utf-8")
    return result


def _collect(job: Path, argv: Sequence[str], wait_s: float) -> CommandOutput:
    deadline = time.monotonic() + wait_s
    while True:
        running = _running(job)
        result = _result(job)
        if result is not None:
            return _deliver(job, argv, result)
        if not running:
            shutil.rmtree(job, ignore_errors=True)
            return CommandOutput(1, (STOPPED_LINE,))
        if time.monotonic() >= deadline:
            return CommandOutput(1, (STILL_RUNNING_LINE,))
        time.sleep(POLL_S)


def run_or_attach(name: str, argv: Sequence[str], start: Start, wait_s: float = ATTACH_WAIT_S) -> CommandOutput:
    """The result of the command `name` on `argv`, waiting up to `wait_s` for it.

    A call whose job is still running waits on it. A call whose job finished reads its result, and
    reads it again while no page changed since. Any other call spends a run and starts the job.
    """
    job = job_folder(name, argv)
    result = _result(job)
    if result is not None and _unread_or_unchanged(job, argv):
        return _deliver(job, argv, result)
    if result is not None or not _running(job):
        if spend_check_or_scenario_run(Path(argv[0])) is None:
            return CommandOutput(1, (CHECK_AND_SCENARIO_RUNS_SPENT_MESSAGE,))
        shutil.rmtree(job, ignore_errors=True)
        job.mkdir(parents=True)
        start(job, argv)
    return _collect(job, argv, wait_s)


def finish_job(job: Path, work: Work, argv: Sequence[str]) -> None:
    """Do the work, and write its result where the next call reads it."""
    try:
        output = work(argv)
    except Exception as failed:
        output = CommandOutput(1, printed_lines((f"the run failed: {type(failed).__name__}: {failed}",)))
    written = job / f"{_RESULT}.tmp"
    _ = written.write_bytes(_OUTPUT.dump_json(output))
    _ = written.replace(job / _RESULT)


def detached(work: Work) -> Start:
    """A start that does the work in a forked process of its own, which outlives the call that started it."""

    def start(job: Path, argv: Sequence[str]) -> None:
        pid = os.fork()
        if pid == 0:
            try:
                _ = os.setsid()
                quiet = os.open(os.devnull, os.O_RDWR)
                for fd in (0, 1, 2):
                    os.dup2(quiet, fd)
                finish_job(job, work, argv)
            finally:
                os._exit(0)
        _ = (job / _PID).write_text(str(pid), encoding="utf-8")

    return start


def settle_jobs(run_dir: Path) -> None:
    """Wait, up to `SETTLE_WAIT_S`, for every job a turn left running, clear them all, and stop the stack its checks kept up, so no two turns run the app at once."""
    folder = jobs_folder(run_dir)
    if folder.is_dir():
        deadline = time.monotonic() + SETTLE_WAIT_S
        for job in folder.iterdir():
            while _running(job) and time.monotonic() < deadline:
                time.sleep(POLL_S)
        shutil.rmtree(folder, ignore_errors=True)
    KeptStack(run_dir, logging.getLogger(__name__)).release()
