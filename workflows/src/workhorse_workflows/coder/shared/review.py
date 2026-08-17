"""The review flow's deterministic work: where to review, what settled, what a human dropped.

Ports `resolve-review-context.py` and `verify-review-resolution.py`.

`check_feedback` used to poll a `feedback.md` in the story's spec dir, resolved through its
own fourth copy of the repo-root walk. It now polls the run's own `inbox.jsonl`
(`Workflow.run_dir`) through `workhorse_workflows.kit.poll_run_inbox`, so this module carries
no repo-root resolution of its own for it.

One divergence is *not* repaired here, and it is a finding rather than a preference:
`verify_review_resolution` looks for the settlement sidecars at a hardcoded
`docs/specs/<slug>`, where the story spine resolves a spec dir through ostler's `spec_path`.
A repo whose specs live elsewhere gets a pass-through gate instead of a settlement — which is
the script's behavior, and changing it here would change which stories the gate binds on.
"""
from __future__ import annotations

import json
import logging

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

#: The agent's structured verdict, and the per-finding ledger ostler writes from it.
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
    """Where the review turns run, and which code repos they may read.

    The docs repo is the reviewer's cwd and is resolved explicitly, never from the launch
    cwd: it is not necessarily the orchestrating repo, and may not be a workspace folder, a
    git repo, or carry an `agents.yml` at all.

    `repo` is the standalone-PR path. With no `plan-context.json` to decode there is nothing
    to derive the affected set from, so the explicitly-named repo *is* the affected set.
    """
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
    docs_path: str = "",
    story_slug: str = "",
    repo_dir: str = "",
) -> ImplResult:
    """Delete the previous cycle's resolution verdict and settlement ledger.

    Findings are labelled positionally — `Finding 1` … `Finding N` — and the labels restart at
    one every time a review runs. So a resolution left over from an earlier cycle names the
    same ids as the review that just replaced it, and `settle-review` verifies the old cycle's
    artifacts against the new cycle's findings and reports every one of them settled. The
    apply turn then correctly reports `no_changes_needed` against a ledger that is already
    green, and a fresh set of required fixes reaches QA having never been applied.

    Clearing here rather than teaching the ids to be unique: the sidecars are outputs of one
    cycle, and a cycle that has not written its own verdict yet has none. An absent resolution
    is already the pass-through case in `verify_review_resolution`, so the first pass of a
    cycle behaves exactly as it does on a story reviewed for the first time.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    if not story_slug:
        logger.warning("no story_slug given — nothing to clear")
        return ImplResult(status="applied", notes="")
    spec_dir = docs_root / "docs" / "specs" / story_slug
    cleared = []
    for name in (RESOLUTION_FILE, SETTLEMENT_FILE):
        stale = spec_dir / name
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
    docs_path: str = "",
    story_slug: str = "",
    claimed_status: str = "applied",
    claimed_notes: str = "",
    repo_dir: str = "",
) -> ImplResult:
    """Fail-closed gate over `apply-review`'s self-reported result. It can only downgrade.

    The apply turn can claim it resolved a finding without doing what the reviewer asked —
    marking a visual-parity finding resolved while capturing no new screenshot, or weakening
    an assertion to mask a mismatch. A prompt mandate cannot prevent that; this can. The
    agent's structured verdict goes to `ostler edit settle-review`, which verifies every
    artifact and assertion it cites against the filesystem **per finding** and writes a
    ledger. This reads the ledger:

    * every finding verified → `applied`, and the loop exits without a full re-review that
      would re-litigate findings already settled;
    * a finding the verdict reports unresolvable → `blocked`, escalated individually;
    * findings still open, addressed but with proof missing or an assertion wrong → the
      gaming case, or simply not done yet → `needs_changes`, re-applying only those;
    * ostler hard-errored on a malformed verdict → `needs_changes`, surfacing why rather
      than spinning on fabricated progress;
    * no verdict sidecar at all → the claim passes through unchanged, so a repo that does
      not emit one keeps the prior behavior instead of being over-blocked.
    """
    docs_root = find_docs_root(docs_path, repo_dir)
    slug = story_slug
    spec_dir = docs_root / "docs" / "specs" / slug
    if not slug or not (spec_dir / RESOLUTION_FILE).is_file():
        logger.info(
            "no %s for %r — passing claimed status %r through",
            RESOLUTION_FILE,
            slug,
            claimed_status,
        )
        return ImplResult(status=claimed_status or "applied", notes=claimed_notes)

    plan = Ostler(docs_root).settle_review(slug, write=True)
    if plan.error:
        reason = plan.error or "ostler settle-review failed"
        logger.warning("ostler settle-review failed for %r: %s", slug, reason)
        return ImplResult(
            status="needs_changes", notes=f"review settlement FAILED: {reason}"
        )

    try:
        ledger = json.loads((spec_dir / SETTLEMENT_FILE).read_text(encoding="utf-8"))
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
    """Poll the run's inbox once, without ever halting or asking.

    The non-blocking counterpart to the operator gate: a human may drop a note into the
    run's inbox at any point while it executes, and the flow checks at safe points whether
    there is an un-consumed one to fold into a single rework pass. "No feedback" is the
    common case, not an error. Polling is what consumes a message — the oldest outstanding
    one is replied to on the way out.
    """
    polled = poll_run_inbox(run_dir, reply_text="folded into a rework pass")
    if polled is None:
        logger.info("no outstanding inbox messages")
        return Feedback()
    content, scope = polled
    logger.info("feedback present (scope=%s)", scope)
    return Feedback(present=True, scope=scope, content=content)


__all__ = [
    "check_feedback",
    "clear_review_resolution",
    "resolve_review_context",
    "verify_review_resolution",
]
