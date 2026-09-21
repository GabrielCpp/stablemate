"""Keep an agent turn from discarding uncommitted work it does not own."""
from __future__ import annotations

import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_OPTIONS_WITH_VALUE = frozenset({"-C", "-c", "--git-dir", "--work-tree", "--namespace",
                                 "--exec-path", "--config-env", "--super-prefix"})

_STASH_READS = frozenset({"list", "show"})

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
    """Why `git <argv>` would discard uncommitted work in a shared tree, or None to run it."""
    command, args = _subcommand(argv)
    options = {arg.split("=", 1)[0] for arg in args if arg.startswith("-")}
    operands = [arg for arg in args if not arg.startswith("-")]
    if command == "stash" and (not operands or operands[0] not in _STASH_READS):
        return "`git stash` sets aside every uncommitted change in the tree, not only yours"
    if command in ("checkout", "switch"):
        return f"`git {command}` overwrites working-tree files other runs are editing"
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
