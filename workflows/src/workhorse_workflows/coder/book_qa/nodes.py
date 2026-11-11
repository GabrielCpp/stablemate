"""The book lane's deterministic spine: coverage, the two plays of the book tool, the memory and the commit."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from workhorse_workflows.coder.shared import commits, paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.docs import CONTEXT_FILE
from workhorse_workflows.coder.shared.schemas.book_qa import (
    BookDeferral,
    BookPlay,
    BookQaRecord,
    CoveredServices,
    ServiceCalls,
)
from workhorse_workflows.coder.shared.schemas.qa import QaFinding
from workhorse_workflows.coder.shared.schemas.queue import StoryCommitted
from workhorse_workflows.coder.shared.story_commit import uncommitted_paths
from workhorse_workflows.coder.shared.worktree import is_product, not_product_roots, untouched_since
from workhorse_workflows.kit import GitError, commit_paths, find_docs_root, find_repo_root
from workhorse_workflows.kit.tools import run_tool

TAIL_LINES = 200
RECORD_FILE = "book-qa.json"
BOOK_OUT = Path("qa") / "book"
BOOK_PAGES = "docs/services"


def book_dir(service: str) -> str:
    """The folder a service's executable book lives in, relative to the repo root."""
    return f"services/{service}"


def _tail(text: str) -> str:
    return "\n".join(text.splitlines()[-TAIL_LINES:])


def _play(argv: list[str], cwd: Path) -> BookPlay:
    done = run_tool(argv, cwd=cwd)
    return BookPlay(exit_code=done.returncode, output=_tail(done.stdout + done.stderr))


@blueprint.node
def covered_services(
    logger: logging.Logger, services: list[str] | None = None, repo_dir: str = ""
) -> CoveredServices:
    """The story's services that have an executable book under the repo root."""
    root = find_repo_root(repo_dir)
    covered = [name for name in services or [] if (root / book_dir(name) / "service.py").is_file()]
    logger.info("%d of %d story service(s) have an executable book", len(covered), len(services or []))
    return CoveredServices(services=covered)


@blueprint.node
def book_check(logger: logging.Logger, service: str, repo_dir: str = "") -> BookPlay:
    """Build everything the service's book declares, with no stack, and return the exit code and output tail."""
    play = _play([sys.executable, "-m", "ostler.book", "check", f"services.{service}"], find_repo_root(repo_dir))
    logger.info("book check of %s exited %d", service, play.exit_code)
    return play


@blueprint.node
def book_run(
    logger: logging.Logger,
    service: str,
    only: list[str],
    copy: str,
    out_dir: str,
    repo_dir: str = "",
) -> BookPlay:
    """Play the named calls of the service's book against the run's copy of the stack."""
    argv = [
        sys.executable, "-m", "ostler.book", "run", f"services.{service}",
        "--only", ",".join(only), "--copy", copy, "--out", out_dir,
    ]
    play = _play(argv, find_repo_root(repo_dir))
    logger.info("book run of %s over %d call(s) exited %d", service, len(only), play.exit_code)
    return play


@blueprint.node
def read_book_record(logger: logging.Logger, spec_dir: str) -> BookQaRecord:
    """The calls a passed check of this story played, or an empty record when none did."""
    return _load_record(Path(spec_dir))


def _load_record(spec: Path) -> BookQaRecord:
    record = spec / RECORD_FILE
    if not record.is_file():
        return BookQaRecord()
    return BookQaRecord.model_validate(json.loads(record.read_text(encoding="utf-8")))


@blueprint.node
def write_book_record(
    logger: logging.Logger,
    spec_dir: str,
    services: list[ServiceCalls],
    findings: list[QaFinding] | None = None,
    unreached: list[str] | None = None,
) -> BookQaRecord:
    """Record the calls a passed check played, the findings it stood on and the claims the book could not state, so a second visit for the story replays them. A green replay means a declared defect still holds, so its finding still stands."""
    record = BookQaRecord(services=services, findings=findings or [], unreached=unreached or [])
    target = Path(spec_dir) / RECORD_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(record.model_dump(exclude_defaults=True), indent=2) + "\n", encoding="utf-8")
    logger.info("recorded the calls of %d service(s) in %s", len(services), target)
    return record


@blueprint.node
def defer_book_judged(logger: logging.Logger, spec_dir: str, repo_dir: str = "") -> BookDeferral:
    """Mark each required obligation under a recorded service's book pages as deferred to that book, in the QA context packet. A missing record, or one with findings, marks nothing."""
    root = find_docs_root(repo_dir)
    spec = root / spec_dir
    record = _load_record(spec)
    context_path = spec / CONTEXT_FILE
    if not record.services or record.findings or not context_path.is_file():
        logger.info("no service book judged this story clean, so no obligation is deferred")
        return BookDeferral()
    context = json.loads(context_path.read_text(encoding="utf-8"))
    marked: dict[str, int] = {}
    for obligation in context.get("obligations") or []:
        if not isinstance(obligation, dict) or obligation.get("required", True) is False:
            continue
        if isinstance(obligation.get("deferred"), dict):
            continue
        page = str(obligation.get("node") or "").partition("#")[0]
        for entry in record.services:
            if page.startswith(f"{BOOK_PAGES}/{entry.service}/"):
                obligation["deferred"] = {
                    "kind": "book",
                    "detail": f"judged by the executable book of {entry.service}",
                }
                marked[entry.service] = marked.get(entry.service, 0) + 1
                break
    if marked:
        context_path.write_text(json.dumps(context, indent=2) + "\n", encoding="utf-8")
    for name, count in marked.items():
        logger.info("deferred %d obligation(s) to the book of %s", count, name)
    return BookDeferral(marked=marked)


@blueprint.node
def commit_service_book(
    logger: logging.Logger,
    services: list[str],
    story_slug: str = "",
    story_id: str = "",
    epic: str = "",
    preexisting: list[str] | None = None,
    repo_dir: str = "",
) -> StoryCommitted:
    """Commit the changed paths under each covered service's book. A product path the seat changed outside those folders is returned in `refused`, and nothing is committed."""
    slug = story_slug or "story"
    root = find_repo_root(repo_dir)
    folders = [(root / book_dir(name)).resolve() for name in services]
    excused = untouched_since(root, tuple(preexisting or ()))
    excluded = not_product_roots(repo_dir, book=False)
    inside: list[str] = []
    stray: list[str] = []
    for rel in uncommitted_paths(root):
        if rel in excused or paths.is_gate_context(rel):
            continue
        if any((root / rel).resolve().is_relative_to(folder) for folder in folders):
            inside.append(rel)
        elif is_product(root, rel, excluded):
            stray.append(rel)
    if stray:
        listing = "\n".join(f"- `{rel}`" for rel in stray)
        return StoryCommitted(
            refused=(
                "These paths changed outside the covered services' books, and the book pass may "
                f"edit only under {', '.join(book_dir(n) + '/' for n in services)}:\n\n{listing}\n\n"
                "Restore each one."
            )
        )
    if not inside:
        logger.info("the book pass left no uncommitted book path for %s", slug)
        return StoryCommitted()
    message = commits.message(
        "test",
        commits.scope(root.name),
        f"play {slug} in the service book",
        epic=epic,
        story=story_id or slug,
    )
    try:
        landed = commit_paths(root, message, *inside, verify=False)
    except GitError as exc:
        return StoryCommitted(refused=f"git refused the commit for {slug} in {root}: {exc}")
    logger.info("committed %d service book path(s) for %s", len(inside), slug)
    return StoryCommitted(committed=landed)


__all__ = [
    "BOOK_OUT",
    "RECORD_FILE",
    "book_check",
    "book_dir",
    "book_run",
    "commit_service_book",
    "defer_book_judged",
    "covered_services",
    "read_book_record",
    "write_book_record",
]
