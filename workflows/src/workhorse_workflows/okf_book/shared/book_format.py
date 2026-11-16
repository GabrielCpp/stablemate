"""What the book format changed since a book was last judged against it: the mark a book records and the commits of the writer's instructions after it."""
from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
import workhorse_workflows
from workhorse_workflows.kit.tools import run_tool
from workhorse_workflows.okf_book.shared.blueprint import blueprint

SKILL_DIR = "base-library/library/skills/ostler/ostler-book"
MARK_FILE = "FORMAT"
DIFF_LIMIT_CHARS = 60000
EMPTY_TREE = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"


class FormatCommit(BaseModel):
    """One commit of the writer's instructions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha: str
    subject: str


class FormatDelta(BaseModel):
    """The mark a book was judged against, the head of the writer's instructions, and the commits and diff between them."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mark: str = ""
    derived: bool = False
    head: str = ""
    commits: list[FormatCommit] = Field(default_factory=list)
    diff: str = ""
    unreadable: str = ""

    @property
    def behind(self) -> bool:
        return bool(self.commits)


def history_repo() -> Path | None:
    """The stablemate checkout the workflow package runs from, or None where the package sits outside one."""
    for folder in Path(workhorse_workflows.__file__).resolve().parents:
        if (folder / SKILL_DIR).is_dir() and (folder / ".git").exists():
            return folder
    return None


def mark_path(book_root: Path, service: str) -> Path:
    return book_root / "services" / service / MARK_FILE


class _Unreadable(Exception):
    pass


def _git(logger: logging.Logger, repo: Path, *args: str) -> str:
    argv = ["git", "-C", str(repo), *args]
    done = run_tool(argv, logger=logger)
    if done.returncode != 0:
        printed = f"{done.stdout}\n{done.stderr}".strip()
        raise _Unreadable(f"`{' '.join(argv)}` exited {done.returncode} and printed: {printed}")
    return done.stdout.strip()


def _book_date(logger: logging.Logger, book_root: Path, service: str) -> str:
    done = run_tool(["git", "-C", str(book_root), "log", "-1", "--format=%cI", "--", f"services/{service}"], logger=logger)
    return done.stdout.strip() if done.returncode == 0 else ""


def _cut(diff: str, history: Path) -> str:
    if len(diff) <= DIFF_LIMIT_CHARS:
        return diff
    return f"{diff[:DIFF_LIMIT_CHARS]}\n[the diff is cut here: read each commit with `git -C {history} show <sha> -- {SKILL_DIR}`]"


def _readable(_logger: logging.Logger, *_args: object) -> FormatDelta:
    return FormatDelta()


@blueprint.node(stub=_readable)
def book_format_delta(logger: logging.Logger, book_root: Path, service: str, history: str) -> FormatDelta:
    """Read the commits of the writer's instructions that a book has not been judged against, from its FORMAT mark or, where it has none, from the last instructions commit before the book's own last commit."""
    repo = Path(history) if history else history_repo()
    if repo is None:
        return FormatDelta(unreadable=f"no checkout holding `{SKILL_DIR}` was found above the workflow package, and no history was named")
    path = mark_path(book_root, service)
    try:
        head = _git(logger, repo, "rev-list", "-1", "HEAD", "--", SKILL_DIR)
        derived = not path.is_file()
        written = _book_date(logger, book_root, service) if derived else ""
        if not derived:
            mark = path.read_text(encoding="utf-8").strip()
        elif written:
            mark = _git(logger, repo, "rev-list", "-1", f"--before={written}", "HEAD", "--", SKILL_DIR)
        else:
            mark = head
        span = f"{mark}..HEAD" if mark else "HEAD"
        listed = _git(logger, repo, "log", "--reverse", "--format=%H%x09%s", span, "--", SKILL_DIR)
        diff = _git(logger, repo, "diff", mark or EMPTY_TREE, "HEAD", "--", SKILL_DIR) if listed else ""
    except _Unreadable as unreadable:
        return FormatDelta(unreadable=str(unreadable))
    commits = [FormatCommit(sha=sha, subject=subject) for sha, _, subject in (line.partition("\t") for line in listed.splitlines())]
    return FormatDelta(mark=mark, derived=derived, head=head, commits=commits, diff=_cut(diff, repo))


def _marked(_logger: logging.Logger, *_args: object) -> None:
    return None


@blueprint.node(stub=_marked)
def mark_book_format(logger: logging.Logger, book_root: Path, service: str, head: str) -> None:
    """Record the commit of the writer's instructions a book was judged against, in the book's package."""
    path = mark_path(book_root, service)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(f"{head}\n", encoding="utf-8")
    logger.info("%s: format mark %s", service, head)
