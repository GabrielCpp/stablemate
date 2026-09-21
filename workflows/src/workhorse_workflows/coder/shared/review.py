"""The review flow's deterministic work: where to review, what settled, what a human dropped."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from ostler import Ostler
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import ImplResult
from workhorse_workflows.coder.shared.schemas.review import Feedback, ReviewContext
from workhorse_workflows.kit import (
    find_docs_root,
    get_affected_repos,
    load_json,
    poll_run_inbox,
    resolve_workspace,
)

RESOLUTION_FILE = "review-resolution.json"
SETTLEMENT_FILE = "review-settlement.json"


@blueprint.node
def resolve_review_context(
    logger: logging.Logger,
    spec_dir: str = "",
    repo: str = "",
    docs_path: str = "",
    repo_dir: str = "",
    workspace_file: str = "",
) -> ReviewContext:
    """Where the review turns run, and which code repos they may read."""
    root = find_docs_root(docs_path, repo_dir)
    plan_ctx = (
        load_json(root / spec_dir / "plan-context.json", "plan-context.json", logger)
        if spec_dir
        else {}
    )
    repos = resolve_workspace(workspace_file, repo_dir)
    names = [repo] if (not plan_ctx and repo) else get_affected_repos(plan_ctx, repos)
    return ReviewContext(
        docs_repo_path=str(root),
        affected_repo_paths=[repos[name]["path"] for name in names if name in repos],
    )


@blueprint.node
def clear_review_resolution(
    logger: logging.Logger,
    spec_dir: str = "",
    story_slug: str = "",
) -> ImplResult:
    """Delete the previous cycle's resolution verdict and settlement ledger."""
    if not story_slug:
        logger.warning("no story_slug given — nothing to clear")
        return ImplResult(status="applied", notes="")
    specs = Path(spec_dir)
    cleared = []
    for name in (RESOLUTION_FILE, SETTLEMENT_FILE):
        stale = specs / name
        if stale.is_file():
            stale.unlink()
            cleared.append(name)
    if cleared:
        logger.info(
            "cleared last cycle's review sidecars for %r: %s",
            story_slug,
            ", ".join(cleared),
        )
    return ImplResult(status="applied", notes=", ".join(cleared))


@blueprint.node
def verify_review_resolution(
    logger: logging.Logger,
    spec_dir: str = "",
    docs_path: str = "",
    story_slug: str = "",
    repo_dir: str = "",
) -> ImplResult:
    """Fail-closed gate over `apply-review`'s self-reported result."""
    docs_root = find_docs_root(docs_path, repo_dir)
    slug = story_slug
    specs = Path(spec_dir)
    if not slug or not (specs / RESOLUTION_FILE).is_file():
        logger.warning("no %s for %r — the apply turn wrote no verdict", RESOLUTION_FILE, slug)
        return ImplResult(
            status="needs_changes",
            notes=(
                f"review settlement: no {RESOLUTION_FILE} was written, so nothing was "
                "verified — re-applying."
            ),
        )

    plan = Ostler(docs_root).settle_review(slug, write=True)
    if plan.error:
        reason = plan.error or "ostler settle-review failed"
        logger.warning("ostler settle-review failed for %r: %s", slug, reason)
        return ImplResult(
            status="needs_changes", notes=f"review settlement FAILED: {reason}"
        )

    try:
        ledger = json.loads((specs / SETTLEMENT_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("settlement ledger unreadable after settle-review (%s)", exc)
        return ImplResult(
            status="needs_changes",
            notes=f"settlement ledger unreadable after settle-review ({exc})",
        )

    if ledger.get("any_blocked"):
        ids = ", ".join(ledger.get("blocked", [])) or "a finding"
        logger.info("review settlement blocked for %r: %s", slug, ids)
        return ImplResult(
            status="blocked",
            notes=f"review settlement: {ids} reported unresolvable (blocked) — escalating.",
        )
    if ledger.get("all_verified"):
        ids = ", ".join(ledger.get("verified", [])) or "all findings"
        logger.info("review settlement applied for %r: %s", slug, ids)
        return ImplResult(
            status="applied",
            notes=(
                f"review settlement: every finding verified against cited artifacts ({ids})."
            ),
        )
    open_ids = (
        ", ".join(f.get("id", "?") for f in ledger.get("open", []) if isinstance(f, dict))
        or "some findings"
    )
    logger.info("review settlement needs_changes for %r: %s still open", slug, open_ids)
    return ImplResult(
        status="needs_changes",
        notes=f"review settlement: {open_ids} still open (proof missing/wrong) — re-applying.",
    )


@blueprint.node
def check_feedback(logger: logging.Logger, run_dir: str = "") -> Feedback:
    """Poll the run's inbox once, without ever halting or asking."""
    polled = poll_run_inbox(run_dir, reply_text="folded into a rework pass")
    if polled is None:
        logger.info("no outstanding inbox messages")
        return Feedback()
    content, scope = polled
    logger.info("feedback present (scope=%s)", scope)
    return Feedback(present=True, content=content)


__all__ = [
    "check_feedback",
    "clear_review_resolution",
    "resolve_review_context",
    "verify_review_resolution",
]
