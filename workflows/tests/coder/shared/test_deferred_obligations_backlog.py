"""A required obligation the book gives no runnable check goes to the backlog for the book, not to the story's QA."""
from __future__ import annotations

import json
import logging
import subprocess
from collections.abc import Callable
from pathlib import Path

from workhorse_workflows.coder.shared.backlog import (
    BOOK_CHECKS_TITLE,
    backlog_bullets,
    file_deferred_obligations,
    select_fix_item,
)
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE

PAGE = "docs/services/web-app/gui/screens/reports.md"
UNTYPED = (
    f"`{PAGE}#empty-alert` sits under a heading that gives its sections no type, "
    "so no `verify:` bullet in it binds to a claim"
)


def _obligation(node: str, detail: str, *, required: bool = True) -> dict:
    return {
        "id": f"okf:{node}:contract",
        "node": node,
        "source": node.partition("#")[0],
        "required": required,
        "deferred": {"kind": "no-verify-declared", "detail": detail},
    }


def _spec(tmp_path: Path, *obligations: dict, services: str = "docs/services") -> str:
    spec = tmp_path / "specs" / "ACME-1"
    spec.mkdir(parents=True)
    context = {"servicesRoot": services, "obligations": [*obligations, {"id": "okf:proved", "required": True}]}
    (spec / CONTEXT_FILE).write_text(json.dumps(context), encoding="utf-8")
    return str(spec)


def _seed(repo: Path, write: Callable[[Path, str], Path], git: Callable[..., subprocess.CompletedProcess]) -> None:
    write(repo / "docs" / "backlog.md", "# Backlog\n\n## Filed by coder\n")
    git(repo, "add", "docs/backlog.md")
    git(repo, "commit", "-qm", "seed the backlog")


def test_each_page_with_deferred_checks_is_filed_once_and_committed(
    repo: Path,
    tmp_path: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    _seed(repo, write, git)
    spec = _spec(
        tmp_path,
        _obligation(PAGE, "the book declares no check for this obligation to prove"),
        _obligation(f"{PAGE}#empty-alert", UNTYPED),
        _obligation(f"{PAGE}#export", UNTYPED.replace("#empty-alert", "#export")),
        _obligation("docs/services/web-app/gui/screens/home.md#banner", "skipped", required=False),
    )

    first = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))
    again = file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))

    backlog = (repo / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert first.appended == 1, first
    assert again.appended == 0, again
    assert [b.id for b in backlog_bullets(backlog, section=BOOK_CHECKS_TITLE)] == [
        "book-checks-web-app-gui-screens-reports"
    ], backlog
    assert "the page itself, `#empty-alert`, `#export`" in backlog, backlog
    assert backlog.count("A section sits under a heading") == 1, backlog
    assert "home.md" not in backlog, backlog
    subject = git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "chore(acme): file the book checks qa could not run", subject


def test_the_fix_lane_leaves_book_checks_for_the_book(
    repo: Path,
    tmp_path: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A book check is the book's to add, and drawing it as a fix story held the passed story's commit for hours."""
    _seed(repo, write, git)
    spec = _spec(tmp_path, _obligation(f"{PAGE}#export", UNTYPED), services=str(repo / "docs" / "services"))

    file_deferred_obligations(logger, spec_dir=spec, repo_dir=str(repo))

    backlog = (repo / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert "[book-checks-web-app-gui-screens-reports]" in backlog, backlog
    assert not select_fix_item(logger, repo_dir=str(repo)).has_fix


def test_a_context_with_nothing_deferred_files_and_commits_nothing(
    repo: Path,
    tmp_path: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    _seed(repo, write, git)
    head = git(repo, "rev-parse", "HEAD").stdout

    drained = file_deferred_obligations(logger, spec_dir=_spec(tmp_path), repo_dir=str(repo))

    assert drained.appended == 0, drained
    assert git(repo, "rev-parse", "HEAD").stdout == head
