"""A QA run's copy of the stack: the books near what it tests, up under the run's lease.

`ostler qa stack` and the workflows bring a stack up through a runbook page. A book with a
`stack.yml` is brought up from it instead, and each function here answers None for a place no
`stack.yml` covers, so its caller keeps the runbook path there.
"""

from __future__ import annotations

from pathlib import Path

from ostler.environments import commands, runtime, spec
from ostler.environments.render import SHARED
from ostler.environments.runtime import Runner, run_command
from ostler.qa import addresses
from ostler.qa.outcome import QaOutcome


def books_near(root: Path, near: Path | None = None) -> list[str]:
    """The books a bring-up near *near* starts: the innermost one holding it, or every book."""
    found = {spec.book_name(root, stack_file): stack_file.parent
             for stack_file in spec.stack_files(root)}
    if near is None:
        return sorted(found)
    here = near.resolve()
    inside = [name for name, directory in found.items() if here.is_relative_to(directory.resolve())]
    return [max(inside, key=lambda name: len(found[name].parts))] if inside else []


def run_env(root: Path, lease: str = "", near: Path | None = None) -> dict[str, str] | None:
    """The lease and the address book a command run against the copy finds in its environment."""
    if not books_near(root, near):
        return None
    copy = runtime.copy_for(root, lease or SHARED)
    env = {addresses.LEASE_ENV: lease} if lease else {}
    env[addresses.BOOK_ENV] = str(copy.directory / runtime.ADDRESSES)
    return env


def up(root: Path, *, lease: str = "", near: Path | None = None,
       runner: Runner = run_command) -> QaOutcome | None:
    """Bring the books near *near* up as the copy *lease* names, or the shared copy without one."""
    books = books_near(root, near)
    if not books:
        return None
    outcome = commands.cmd_up(root, books, copy_name=lease or SHARED, runner=runner)
    data = {**outcome.data, "lease": lease, "ready": "yes" if outcome.ok else "no"}
    if not outcome.ok:
        return QaOutcome(False, f"stack bring-up failed: {outcome.message}", data)
    where = data.get("entry_url") or "(no entry url)"
    return QaOutcome(True, f"stack brought up and healthy at {where}", data)


def down(root: Path, *, lease: str = "", near: Path | None = None,
         runner: Runner = run_command) -> QaOutcome | None:
    """Tear down the copy *lease* names, or the shared copy without one."""
    if not books_near(root, near):
        return None
    outcome = commands.cmd_down(root, copy_name=lease or SHARED, runner=runner)
    data = {**outcome.data, "lease": lease, "torn_down": "yes" if outcome.ok else "no"}
    return QaOutcome(outcome.ok, "stack torn down" if outcome.ok else outcome.message, data)


__all__ = ["books_near", "down", "run_env", "up"]
