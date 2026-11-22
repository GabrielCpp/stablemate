"""The paths a commit of a service's book takes: its own folder and the files it imports from outside it, never the bytecode the plays leave behind."""
from __future__ import annotations

import logging
import sys
from collections.abc import Iterable
from pathlib import Path

from workhorse_workflows.kit.git import open_repo
from workhorse_workflows.kit.tools import run_tool

logger = logging.getLogger(__name__)

CACHE_DIR = "__pycache__"
COMPILED_SUFFIXES = (".pyc", ".pyo")


BOOK_ENV = {"PYTHONDONTWRITEBYTECODE": "1"}


def book_command(*verb: str) -> list[str]:
    """The argv of one `ostler book` verb. Run it with `BOOK_ENV` so a play leaves no compiled file under the book."""
    return [sys.executable, "-m", "ostler.book", *verb]


def is_compiled(path: str | Path) -> bool:
    """Is *path* a compiled file or inside a bytecode folder, which no book commit takes."""
    return CACHE_DIR in Path(path).parts or str(path).endswith(COMPILED_SUFFIXES)


def without_compiled(paths: Iterable[str]) -> list[str]:
    return [path for path in paths if not is_compiled(path)]


def outside_paths(root: Path, module: str) -> tuple[str, ...]:
    """The files under the book root, outside the service's folder, that its book imports, as `ostler book files --outside` lists them. Empty, with a warning, when the verb cannot answer."""
    done = run_tool(book_command("files", module, "--outside"), cwd=root, env=BOOK_ENV)
    if done.returncode != 0:
        logger.warning("could not list the files the book of %s imports, so its commit takes its own folder alone: %s",
                       module, (done.stderr or done.stdout or "").strip()[-300:])
        return ()
    return tuple(line for line in done.stdout.splitlines() if line.strip())


def book_pathspecs(root: Path, module: str) -> tuple[str, ...]:
    """What a commit of the book of *module* stages: its own folder, then the files it imports from outside that folder."""
    return (module.replace(".", "/"), *outside_paths(root, module))


def stageable(root: Path, pathspecs: Iterable[str]) -> list[str]:
    """The files under *pathspecs* a commit may take: tracked ones, untracked ones the ignore file lets through, and staged deletions, with no compiled file among them."""
    specs = list(pathspecs)
    if not specs:
        return []
    git = open_repo(root).git
    found = git.ls_files("--cached", "--others", "--exclude-standard", "--", *specs).splitlines()
    found += git.diff("--cached", "--name-only", "--diff-filter=D", "--", *specs).splitlines()
    return sorted(set(without_compiled(found)))


def left_behind(root: Path, pathspecs: Iterable[str]) -> list[str]:
    """The files under *pathspecs* that are untracked, modified or only staged, so a commit that just ran did not take them. Compiled files do not count."""
    specs = list(pathspecs)
    if not specs:
        return []
    git = open_repo(root).git
    found = git.ls_files("--others", "--modified", "--exclude-standard", "--", *specs).splitlines()
    found += git.diff("--cached", "--name-only", "--", *specs).splitlines()
    return sorted(set(without_compiled(found)))


def left_behind_refusal(paths: Iterable[str]) -> str:
    """The refusal that names each file a book commit left out, or "" when it left none."""
    listing = "\n".join(f"- `{path}`" for path in paths)
    if not listing:
        return ""
    return f"The book commit left these files untracked or modified, and the book needs them to load:\n\n{listing}\n\nCommit or restore each one."
