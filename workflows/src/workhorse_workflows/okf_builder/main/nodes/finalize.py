"""The scoped git commits that record the OKF book: one per turn, and the completed book.

**Every commit here skips the target repo's hooks.** A repo's `pre-commit` and
`commit-msg` hooks are written for whoever changes its code. This workflow commits only
the book it alone writes, and has gated that book with its own doctor. The hook that
blocked it was a generated-file drift check over the whole working tree, so an unrelated
hand edit anywhere in the checkout stopped every book commit (`kit.git.commit_paths`).

**Why a commit per turn.** A run used to leave the book uncommitted until it was clean,
often for days. `HEAD` then predated every edit the run had made, and a repair turn that
restored a file from `HEAD` to undo its own change erased the run's earlier repairs with
it. `commit_turn` runs before and after every turn, so `HEAD` is where the turn started
and `git diff -- <book>` is exactly what the turn wrote. The pre-turn call records
whatever deterministic nodes wrote to the book since the last turn. The post-turn call
records the turn under the subject the turn wrote, because the turn is the only
participant that knows what it changed.
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from git.exc import GitError

from ostler import Ostler
from ostler import doctor as doctor_mod
from ostler import index as index_mod
from ostler import refs as refs_mod
from ostler import stamp as stamp_mod
from workhorse.pyflow import WorkflowFailed
from workhorse_workflows.kit import commit_paths, diff_text
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import Committed, Stamped

_SUBJECT = "docs: update the OKF book"
_SUBJECT_MAX = 72

#: Seconds between attempts when another process holds the index lock.
_LOCK_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)


def _message(story: str, subject: str = _SUBJECT) -> str:
    lines = subject.strip().splitlines()
    head = (lines[0].strip() if lines else "") or _SUBJECT
    if len(head) > _SUBJECT_MAX:
        head = head[: _SUBJECT_MAX - 1].rstrip() + "…"
    story = story.strip()
    return f"{head}\n\nStory: {story}" if story else head


def _book_pathspec(root: Path, features_root: str) -> str:
    book = Path(features_root).resolve()
    try:
        return str(book.relative_to(root))
    except ValueError as exc:
        raise WorkflowFailed(
            f"refusing to commit OKF book outside its repository: {book} is not under {root}",
            failure_class="okf-builder-book-outside-repo",
        ) from exc


@blueprint.node
def commit_turn(
    logger: logging.Logger,
    repo_root: str,
    features_root: str,
    subject: str,
    story: str = "",
    lock_retries: int = len(_LOCK_BACKOFF_S),
) -> Committed:
    """Commit whatever changed in the book, under `subject`; never fail the run.

    A refused commit leaves the edits in the tree, and the next call's scope is the same
    book, so they land with the next commit. The hard stop belongs to `commit_book`, the
    commit that must land. Several runs in one checkout share one index, so a held
    `index.lock` is expected and waited out. That shared index is the property this retry
    handles rather than removes: a run dispatched with `--worktree` has its own index and
    never waits here.
    """
    root = Path(repo_root).resolve()
    pathspec = _book_pathspec(root, features_root)
    message = _message(story, subject)
    for attempt in range(lock_retries + 1):
        try:
            committed = commit_paths(root, message, pathspec, verify=False)
        except GitError as exc:
            locked = "index.lock" in str(exc)
            if locked and attempt < lock_retries:
                time.sleep(_LOCK_BACKOFF_S[min(attempt, len(_LOCK_BACKOFF_S) - 1)])
                continue
            logger.warning(
                "could not commit %s (%s); its edits stay in the tree for the next commit: %s",
                pathspec, "index locked" if locked else "git refused", exc,
            )
            return Committed(committed=False)
        if committed:
            logger.info("committed %s: %s", pathspec, message.splitlines()[0])
        return Committed(committed=committed)
    return Committed(committed=False)


@blueprint.node
def stamp_turn(
    logger: logging.Logger,
    repo_root: str,
    features_root: str,
    pre_turn_sha: str,
    item_kind: str = "",
    item_context: str = "",
    doc_status: str = "",
) -> Stamped:
    """Stamp exactly the `@digest` targets this turn earned, gated by the turn's own errors.

    Two sources of stampable targets, both scoped to what *this* turn actually resolved.
    A `fix:stale-citation` row restamps only the `(node, file)` pairs it was assigned —
    and only when the turn's own `doc_status` says it finished (the `documented` verdict,
    or unstated — the same convention `advance_watermark` gates its own regrounding on).
    A `partial` or `skipped` turn never re-read the citation, so marking it fresh would
    hide that gap; the row simply comes back on the next join, same as an unadvanced
    watermark does. New-citation stamping below stays unconditional even on such a turn:
    it stamps only targets `doctor` already found `unstamped-citation` (never an error),
    on nodes the turn's own diff shows it wrote — doctor gates that claim on its own.
    Any node this turn touched also gets its still-unstamped targets, read off `doctor`'s
    `unstamped-citation` findings on the pages the book-pathspec diff (`HEAD` at turn
    start vs. the working tree now, the same boundary `commit_turn` relies on) shows this
    turn edited. Either way a node carrying an error finding of its own — from this same
    `doctor` pass, scoped to just these pages — is withheld entirely: a stamp asserts the
    citation was re-read and still holds, and a book `doctor` already disagrees with
    cannot make that claim.

    Called from `flow.py` right before the post-turn `commit_turn`, so a stamp lands in
    the same book commit as the edits it is about.
    """
    repo = Path(repo_root).resolve()
    pathspec = _book_pathspec(repo, features_root)
    with index_mod.session(repo):
        graph = Ostler(repo).graph

        touched_pages = {
            line for line in diff_text(repo, "--name-only", pre_turn_sha, "--", pathspec).splitlines()
            if line
        } if pre_turn_sha else set()

        restamp_pairs: list[tuple[str, str]] = []
        if (
            item_kind == "fix:stale-citation"
            and item_context
            and doc_status in ("", "documented")
        ):
            try:
                context = json.loads(item_context)
            except (json.JSONDecodeError, TypeError):
                context = {}
            file_target = str(context.get("file") or "")
            if file_target:
                restamp_pairs = [
                    (str(node_id), file_target) for node_id in context.get("nodes") or ()
                ]

        def _page_of(node_id: str) -> str | None:
            node = graph.find_ui_node(node_id)
            return node.path.relative_to(graph.root).as_posix() if node is not None else None

        scope_pages = set(touched_pages)
        scope_pages.update(page for node_id, _ in restamp_pairs if (page := _page_of(node_id)))
        if not scope_pages:
            return Stamped()

        report = doctor_mod.scope_to_paths(doctor_mod.run(graph), sorted(scope_pages))
        blocked_nodes: set[str] = set()
        blocked_pages: set[str] = set()
        for finding in report.findings:
            if finding.severity != "error":
                continue
            if finding.node:
                blocked_nodes.add(finding.node)
            elif finding.path:
                blocked_pages.add(finding.path)

        def _blocked(node_id: str) -> bool:
            return node_id in blocked_nodes or _page_of(node_id) in blocked_pages

        pairs: list[tuple[str, str]] = []
        skipped: set[str] = set()
        for node_id, file_target in restamp_pairs:
            if _blocked(node_id):
                skipped.add(node_id)
            else:
                pairs.append((node_id, file_target))

        for finding in report.findings:
            if finding.code != "unstamped-citation" or not finding.node or finding.path not in touched_pages:
                continue
            if _blocked(finding.node):
                skipped.add(finding.node)
                continue
            pairs.append((finding.node, refs_mod.ref_path(finding.ref)))

        if not pairs:
            return Stamped(skipped_nodes=sorted(skipped))

        results = stamp_mod.stamp_targets(graph, Path(features_root).resolve(), pairs)
        stamped = sum(r.stamped for r in results)
    if stamped:
        logger.info("stamped %d citation target(s) this turn", stamped)
    return Stamped(stamped=stamped, skipped_nodes=sorted(skipped))


@blueprint.node
def commit_book(
    logger: logging.Logger,
    repo_root: str,
    features_root: str,
    story: str = "",
) -> Committed:
    """Commit only the completed service book, with optional story provenance."""
    root = Path(repo_root).resolve()
    book_pathspec = _book_pathspec(root, features_root)
    committed = commit_paths(root, _message(story), book_pathspec, verify=False)
    logger.info(
        "%s completed OKF book at %s",
        "committed" if committed else "no changes in",
        book_pathspec,
    )
    return Committed(committed=committed)


__all__ = ["commit_book", "commit_turn", "stamp_turn"]
