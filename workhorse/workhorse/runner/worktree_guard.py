"""Keep an agent turn from discarding uncommitted work it does not own.

Several runs can drive agents in one working tree at once, and a workflow that leaves
its progress uncommitted until the end — a docs drain that commits only a clean book —
keeps every run's work in that shared tree for hours. Git's restoring commands cannot
tell whose uncommitted change they are throwing away: an agent that runs `git stash`
to see "the file before my edit", then pops it, silently drops every edit another run
made in between, and `git checkout -- <path>` does the same to a single file. A
prompt that says "never run git" does not hold; the turn that ignores it looks like
any other.

So the prevention sits where the command is issued. While a workflow that declares
`PROTECT_WORKTREE` runs an agent turn, the turn's `PATH` starts with a directory whose
`git` is this file: it refuses the commands in `refusal` with a message saying how to
get the same answer without touching the tree, and hands every other invocation to the
real `git` unchanged. Deterministic nodes run in the driver's own process and never see
the shim, so a workflow's own commit step is unaffected.

This module is copied verbatim to be that shim, which is why it imports nothing but
the standard library: the copy runs on every `git` an agent issues, and must start in
milliseconds with no package on its path.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

#: Global options that take their value as the NEXT argument, so the subcommand is not
#: mistaken for the value. `--git-dir=x` spells its value inline and needs no entry.
_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                                 "--exec-path", "--config-env", "--super-prefix"})

#: `git stash` subcommands that only read.
_STASH_READS = frozenset({"list", "show"})

#: `git reset` modes that rewrite the working tree. A bare or `--soft`/`--mixed` reset
#: moves only HEAD and the index.
_RESET_REWRITES = frozenset({"--hard", "--merge", "--keep"})

_ALTERNATIVE = (
    "To see a file as committed, run `git show HEAD:<path>`; to see what changed in it, "
    "`git diff -- <path>`. To undo your own edit, edit the file back."
)

_ACTIVE: ContextVar[Path | None] = ContextVar("worktree_guard", default=None)


def _subcommand(argv: list[str]) -> tuple[str, list[str]]:
    """Split `argv` (what follows `git`) into its subcommand and that command's arguments."""
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in _OPTIONS_WITH_VALUE:
            index += 2
        elif arg.startswith("-"):
            index += 1
        else:
            return arg, argv[index + 1:]
    return "", []


def refusal(argv: list[str]) -> str | None:
    """Why `git <argv>` would discard uncommitted work in a shared tree, or None to run it.

    The set is the commands that overwrite or remove working-tree content they did not
    write: every stash but a read (a stash pop restores the tree to the stash's moment,
    dropping what landed since), `checkout`/`switch` (a path checkout discards that
    file's edits, a branch switch rewrites the tree under every other run), `restore`
    unless it touches only the index, a tree-rewriting `reset`, and a `clean` that
    deletes.
    """
    command, args = _subcommand(argv)
    options = {arg.split("=", 1)[0] for arg in args if arg.startswith("-")}
    operands = [arg for arg in args if not arg.startswith("-")]
    if command == "stash" and (not operands or operands[0] not in _STASH_READS):
        return "`git stash` sets aside every uncommitted change in the tree, not only yours"
    if command in ("checkout", "switch"):
        return f"`git {command}` overwrites working-tree files other runs are editing"
    # Only an index-only restore is safe; `--staged --worktree` still rewrites the tree.
    if command == "restore" and (options & {"--worktree", "-W"} or not options & {"--staged", "-S"}):
        return "`git restore` discards working-tree edits other runs made"
    if command == "reset" and options & _RESET_REWRITES:
        return "a tree-rewriting `git reset` discards every uncommitted change in the tree"
    if command == "clean" and not options & {"-n", "--dry-run"}:
        return "`git clean` deletes untracked files other runs just wrote"
    return None


def _real_git(shim_dir: Path) -> str | None:
    """The first `git` on `PATH` that is not this shim."""
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if not entry or Path(entry).resolve() == shim_dir:
            continue
        candidate = Path(entry) / "git"
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def main(argv: list[str]) -> int:
    """Refuse a discarding command, else become the real `git`."""
    reason = refusal(argv)
    if reason is not None:
        sys.stderr.write(
            f"refused: {reason}. This working tree is shared with other runs, and their "
            f"uncommitted work would be lost. {_ALTERNATIVE}\n"
        )
        return 1
    real = _real_git(Path(__file__).resolve().parent)
    if real is None:
        sys.stderr.write("git: no git executable on PATH besides the worktree guard\n")
        return 127
    os.execv(real, [real, *argv])
    return 0  # pragma: no cover - execv does not return


def install(root: Path) -> Path:
    """Write the shim under `root` (if it is not already current) and return its directory."""
    shim_dir = root / "worktree-guard"
    shim = shim_dir / "git"
    body = f"#!{sys.executable}\n" + Path(__file__).read_text(encoding="utf-8")
    if not shim.is_file() or shim.read_text(encoding="utf-8") != body:
        shim_dir.mkdir(parents=True, exist_ok=True)
        tmp = shim.with_suffix(".tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.chmod(0o755)
        tmp.replace(shim)
    return shim_dir.resolve()


@contextmanager
def guarding(root: Path) -> Iterator[None]:
    """Run the enclosed agent turns with the shim installed under `root` first on `PATH`."""
    token = _ACTIVE.set(install(root))
    try:
        yield
    finally:
        _ACTIVE.reset(token)


def guarded_path(path: str) -> str:
    """`path` with the active shim directory prepended, or unchanged outside `guarding`."""
    shim_dir = _ACTIVE.get()
    if shim_dir is None:
        return path
    return os.pathsep.join([str(shim_dir), *(entry for entry in path.split(os.pathsep) if entry)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
