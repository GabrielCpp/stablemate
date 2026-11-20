"""Bring a book's stack up and run its plan through ostler — family-neutral."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

from ostler import Ostler
from ostler.environments import leases, runtime, spec
from ostler.environments.render import SHARED
from ostler.qa import devices, stack
from ostler.qa.outcome import QaOutcome

from workhorse_workflows.kit.qa.schemas import QaPlanRun, QaStatus, StackStatus
from workhorse_workflows.kit import find_book_root, find_docs_root
from workhorse_workflows.kit.leased_env import scoped_envs
from workhorse_workflows.kit.qa.support import QA_PLAN_FILE, notes_for

RUN_STATUSES: dict[str, QaStatus] = {
    "passed": "passed",
    "failed": "failed",
    "blocked": "blocked",
    "invalid": "invalid",
}

def story_near(root: Path, services: Sequence[str] = ()) -> str:
    """The one named service whose book has a stack file beside it, else nothing."""
    beside = [
        name
        for name in dict.fromkeys(services)
        if (root / spec.BOOKS_DIR / name / spec.OPS_DIR / spec.STACK_FILE).is_file()
    ]
    return str(root / spec.BOOKS_DIR / beside[0]) if len(beside) == 1 else ""


def copy_lease(*parts: str) -> str:
    """The lease a run names its stack copy with: *parts* joined, lowercased, and reduced to what a container name takes."""
    joined = "-".join(part for part in parts if part).lower()
    return re.sub(r"[^a-z0-9_-]+", "-", joined).lstrip("-_")


def stack_env(root: Path, near: str = "", lease: str = "") -> dict[str, str]:
    """What a command run against the stack *near* selects finds in its environment: the lease and its book."""
    return leases.run_env(root, lease, Path(near) if near else None, holder=os.getpid()) or {}


def release_copy(
    logger: logging.Logger,
    repo_dir: str = "",
    near: str = "",
    lease: str = "",
) -> QaOutcome | None:
    """Tear down the copy *lease* holds of a per-run stack, or None when the stack is shared and stays serving."""
    root = find_book_root(repo_dir)
    near_path = Path(near) if near else None
    if not lease or not leases.books_near(root, near_path):
        return None
    return leases.down(root, lease=lease, near=near_path)


def teardown_stack(logger: logging.Logger, repo_dir: str = "") -> QaOutcome:
    """Tear down the shared stack when this run brought it up, and leave one already serving."""
    root = find_book_root(repo_dir)
    if not leases.books_near(root):
        return QaOutcome(True, "no book declares a stack", {"torn_down": "skipped"})
    started = runtime.read_manifest(runtime.copy_for(root, SHARED).directory).get("started_by")
    if started != runtime.holder_stamp(os.getpid()):
        _ = runtime.release_holder(root, SHARED, os.getpid())
        return QaOutcome(True, "the stack was up before this run, so it stays serving",
                         {"torn_down": "skipped"})
    copied = leases.down(root)
    return copied or QaOutcome(True, "no book declares a stack", {"torn_down": "skipped"})


def hold_copy(repo_dir: str = "", lease: str = "") -> bool:
    """Name this process as the holder of the run's copy, so a resumed run keeps what it leased."""
    if not lease:
        return False
    return runtime.hold(find_book_root(repo_dir), lease, os.getpid())


def ensure_stack(
    logger: logging.Logger,
    repo_dir: str = "",
    near: str = "",
    lease: str = "",
) -> StackStatus:
    """Bring the durable QA stack up (or adopt one already serving) before the runner."""
    root = find_book_root(repo_dir)
    near_path = Path(near) if near else None
    copied = leases.up(root, lease=lease, near=near_path, holder=os.getpid())
    if copied is None:
        return StackStatus(
            ready="unneeded",
            notes=("No service book declares `ops/stack.yml` near this story, so there is no "
                   "stack to bring up."),
        )
    if not copied.ok:
        return _copy_status(copied)
    booted = devices.bring_up_book_devices(
        root, near=near_path,
        env=leases.run_env(root, lease, near_path, holder=os.getpid()), logger=logger)
    if booted and booted[-1].get("ready") != "yes":
        last = booted[-1]
        return StackStatus(
            ready="no", failed_step=last.get("failed_step", ""),
            notes=device_failure(
                last.get("failed_step", "unknown"), (last.get("error") or "").strip(),
                (last.get("manifest") or {}).get("stack_file") or last.get("source", "")))
    return _copy_status(copied)


def _copy_status(outcome: QaOutcome) -> StackStatus:
    if outcome.ok:
        return StackStatus(ready="yes", entry_url=str(outcome.data.get("entry_url", "")),
                           notes=f"Stack {outcome.message.removeprefix('stack ')}.")
    return StackStatus(ready="no", failed_step="stack.yml", notes=outcome.message)


def release_stack(logger: logging.Logger, owned_pgids: tuple[str, ...]) -> None:
    """Stop the process groups a bring-up started, newest first, and leave an adopted one up.

    It never raises, because ostler's teardown fails soft on a process group, so a caller releases
    in a `finally` and a failure of the work it wraps is never masked.
    """
    for pgid in reversed(owned_pgids):
        _ = stack.teardown_app(pgid, "", "", logger=logger)


def _group_running(pgid: int) -> bool:
    """Whether a process other than a zombie is left in the process group *pgid*."""
    for stat in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = stat.read_text(encoding="ascii", errors="replace").rpartition(")")[2].split()
        except OSError:
            continue
        if len(fields) > 2 and fields[2] == str(pgid) and fields[0] != "Z":
            return True
    return False


def stack_stopped(owned_pgids: tuple[str, ...]) -> str:
    """Why the app stopped serving: a process group bring-up launched and left serving has no process left, or nothing when each still runs.

    Bring-up owns a group only when its launch command was still running once the app answered,
    and only when the group still runs once every stack is up, since a later stack's bring-up
    reaps a server an earlier one left on the same port. A group that empties afterwards is a
    server that exited, never a bring-up that handed off.
    """
    for pgid in owned_pgids:
        if pgid.isdigit() and not _group_running(int(pgid)):
            return (f"the server the stack's bring-up launched (process group {pgid}) exited during the run, "
                    "so the app stopped serving and no later scenario could reach it; the step that "
                    "launches it must start a server that keeps serving until the run stops it, with no "
                    "time limit of its own")
    return ""


def device_failure(step: str, error: str, stack_file: str) -> str:
    """Why a device step failed, and the book's stack file whose step repairs it."""
    failed = f"Device step '{step}' failed" + (f": {error}" if error else "")
    return f"{failed}. Repair that step under `device:` in `{stack_file}`."


def _untracked(root: Path) -> set[str]:
    """The untracked files git would offer to commit in *root*, none when it is no checkout."""
    done = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--others", "--exclude-standard"],
        capture_output=True, text=True, check=False,
    )
    return {name for name in done.stdout.split("\0") if name} if done.returncode == 0 else set()


def _remove_files_left_since(root: Path, before: set[str], evidence: Path, logger: logging.Logger) -> None:
    """Remove the untracked files a plan's commands left in the checkout, so none reaches the story's commit; the run's evidence stays."""
    for name in sorted(_untracked(root) - before):
        path = root / name
        if path.resolve().is_relative_to(evidence):
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
        logger.info("removed %s, left by the QA plan", name)
        parent = path.parent
        while parent != root and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def run_qa_plan(
    logger: logging.Logger,
    spec_dir: str = "",
    repo_dir: str = "",
    only: list[str] | None = None,
    plan_file: str | None = None,
    near: str = "",
    lease: str = "",
    label: str | None = None,
) -> QaPlanRun:
    """Execute the QA plan through ostler and normalize its four-state outcome."""
    docs_root = find_docs_root(repo_dir)
    plan = plan_file if plan_file is not None else str(Path(spec_dir) / QA_PLAN_FILE)
    leased = stack_env(find_book_root(repo_dir), near=near, lease=lease)
    before = _untracked(docs_root)
    with scoped_envs(leased):
        outcome = Ostler(docs_root).qa_run(plan, spec=spec_dir, only=only, label=label)
    _remove_files_left_since(docs_root, before, (docs_root / spec_dir).resolve(), logger)
    status = RUN_STATUSES.get(outcome.status.lower(), "invalid")
    notes = notes_for(outcome, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    return QaPlanRun(status=status, notes=notes, ostler=outcome.data)


__all__ = ["copy_lease", "ensure_stack", "hold_copy", "release_copy", "run_qa_plan", "stack_env", "stack_stopped", "story_near", "teardown_stack"]
