"""The scoped git commits that record the OKF book: one per turn, and the completed book."""
from __future__ import annotations

import json
import logging
import re
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

_LOCK_BACKOFF_S = (1.0, 2.0, 4.0, 8.0)

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _edited_ranges(repo: Path, pre_turn_sha: str, pathspec: str) -> dict[str, list[tuple[int, int]]]:
    """Per-file line ranges (1-based, end-exclusive) this turn's diff actually touched."""
    ranges: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in diff_text(repo, "--unified=0", pre_turn_sha, "--", pathspec).splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            current = path[2:] if path.startswith("b/") else None
            continue
        match = _HUNK_RE.match(line)
        if match and current:
            start = int(match.group(1))
            count = int(match.group(2)) if match.group(2) is not None else 1
            end = start + count if count else start + 1
            ranges.setdefault(current, []).append((start, end))
    return ranges


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
    """Commit whatever changed in the book, under `subject`; never fail the run."""
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
    """Stamp exactly the `@digest` targets this turn earned, gated by the turn's own errors."""
    repo = Path(repo_root).resolve()
    pathspec = _book_pathspec(repo, features_root)
    with index_mod.session(repo):
        graph = Ostler(repo).graph

        edited_ranges = _edited_ranges(repo, pre_turn_sha, pathspec) if pre_turn_sha else {}
        touched_pages = set(edited_ranges)

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

        def _node_edited(node_id: str) -> bool:
            ranges = edited_ranges.get(_page_of(node_id) or "")
            if not ranges:
                return False
            node = graph.find_ui_node(node_id)
            if node is None:
                return False
            lo, hi = stamp_mod.node_line_range(graph, node)
            return any(lo < r_hi and r_lo < hi for r_lo, r_hi in ranges)

        def _restamp_blocked(node_id: str, file_target: str) -> bool:
            if _page_of(node_id) in blocked_pages:
                return True
            for finding in report.findings:
                if finding.severity != "error" or finding.node != node_id:
                    continue
                if finding.code == "stale-citation" and refs_mod.ref_path(finding.ref) == file_target:
                    continue
                return True
            return False

        pairs: list[tuple[str, str]] = []
        skipped: set[str] = set()
        for node_id, file_target in restamp_pairs:
            if _restamp_blocked(node_id, file_target):
                skipped.add(node_id)
            else:
                pairs.append((node_id, file_target))

        for finding in report.findings:
            if finding.code != "unstamped-citation" or not finding.node or finding.path not in touched_pages:
                continue
            if not _node_edited(finding.node):
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
