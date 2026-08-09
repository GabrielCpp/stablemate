"""The review flow's deterministic work: where to review, what settled, what a human dropped.

Ports `resolve-review-context.py`, `verify-review-resolution.py` and `check_feedback.py`.

`check_feedback.py` carried its own `_find_repo_root(repo_dir)` — a fourth copy of the repo-root
/ cwd-if-root / ancestor-walk sequence, written out because the script was stdlib-only and
could not import `workhorse.scriptutil`. A node has no such constraint, so it calls
`paths.launch_repo_root(repo_dir)` like everything else in this package. The resolution order is the
same one the script implemented.

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
from workhorse import gates
from workhorse_workflows.kit import find_docs_root, load_json
from workhorse_workflows.coder.shared import paths
from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import ImplResult
from workhorse_workflows.coder.shared.schemas.review import Feedback, ReviewContext
from workhorse_workflows.kit import get_affected_repos, resolve_workspace

#: The agent's structured verdict, and the per-finding ledger ostler writes from it.
RESOLUTION_FILE = "review-resolution.json"
SETTLEMENT_FILE = "review-settlement.json"

#: The two states the feedback inbox can be in. Reading `NEW` is what consumes it: the node
#: stamps `CONSUMED` on the way out, so one dropped note buys exactly one rework pass rather
#: than a loop. The `STATUS:`/`SCOPE:` header itself is read through `workhorse.gates` —
#: these names are this inbox's vocabulary, which that reader deliberately does not know.
NEW = "NEW"
CONSUMED = "CONSUMED"


def _scope_of(text: str) -> str:
    """The inbox's `SCOPE:` line. Only `epic` is honoured; anything else is `story`."""
    return "epic" if gates.scope_of(text) == "epic" else "story"


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
def check_feedback(
    logger: logging.Logger, feedback_path: str = "", repo_dir: str = ""
) -> Feedback:
    """Poll the story's feedback inbox once, without ever halting or asking.

    The non-blocking counterpart to the operator gate: a human may drop notes into
    `<spec_dir>/feedback.md` at any point while the run executes, and the flow checks at safe
    points whether there are un-consumed ones to fold into a single rework pass. "No feedback"
    is the common case, not an error.

    A file with real content but no `STATUS:` line is treated as new — forgiving for a human
    who pasted notes without the header — and stamped `CONSUMED` at the top. Whitespace-only
    is nothing.
    """
    if not feedback_path:
        logger.info("no feedback_path given — nothing to poll")
        return Feedback()

    # `root / path` yields `path` when it is absolute, so repo-relative and absolute inbox
    # paths both work.
    inbox = paths.launch_repo_root(repo_dir) / feedback_path
    if not inbox.exists():
        logger.info("no inbox file at %s — nothing to poll", inbox)
        return Feedback()

    current = inbox.read_text(encoding="utf-8")
    state = gates.status_of(current)

    if state == NEW:
        inbox.write_text(gates.set_status(current, CONSUMED), encoding="utf-8")
        logger.info("consumed NEW feedback from %s", inbox)
        return Feedback(present=True, scope=_scope_of(current), content=current)

    if state == "":
        if current.strip():
            # `set_status` prepends the header when the file has none, which is what a
            # hand-dropped note without one needs: it too is consumed exactly once.
            inbox.write_text(gates.set_status(current, CONSUMED), encoding="utf-8")
            logger.info("no STATUS line but %s has content — treating as NEW", inbox)
            return Feedback(present=True, scope=_scope_of(current), content=current)
        logger.info("no STATUS line and %s is empty — nothing to do", inbox)
        return Feedback()

    logger.info("%s is %s — nothing new", inbox, state)
    return Feedback()


__all__ = ["check_feedback", "resolve_review_context", "verify_review_resolution"]
