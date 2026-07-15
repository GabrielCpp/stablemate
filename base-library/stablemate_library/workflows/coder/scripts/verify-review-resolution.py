#!/usr/bin/env python3
"""Deterministic, fail-closed gate over apply-review's self-reported result.

apply-review can CLAIM it resolved a review finding without doing the work the
reviewer asked for (e.g. mark a visual-parity finding "resolved" while capturing no
new screenshot, or weaken an assertion to mask a mismatch). A prompt mandate can't
prevent that; this gate can only DOWNGRADE a claimed pass.

It hands the agent's structured verdict (``<spec_dir>/review-resolution.json``) to
``ostler edit settle-review`` — the single tool that owns the story-status transition —
which verifies every artifact/assertion the verdict cites against the filesystem **per
finding** and writes a settlement ledger (``<spec_dir>/review-settlement.json``) plus,
when warranted, the story-status transition. This script reads that ledger and
translates the per-finding outcome into the authoritative ``impl_result`` the review
loop branches on (4.3 granularity — fix and settle findings one at a time):

  - every finding verified (story → "Review fixes applied")          → status "applied"
    (decide_apply_review approves and exits the loop — no full re-review to re-litigate
    already-settled findings);
  - a finding the verdict reports unresolvable (story → "Blocked")    → status "blocked"
    (decide_apply_review escalates THAT finding to the operator individually);
  - one or more findings still open — addressed but their cited proof is missing or an
    assertion is wrong (the gaming case, or just not done yet)         → status
    "needs_changes" (re-applies only the open findings, targeted; bounded by guard_review);
  - ostler hard-errored (malformed verdict — no findings / unknown disposition)
                                                                       → status "needs_changes";
  - no review-resolution.json present (story didn't use the structured verdict)
                                                                       → pass the agent's
    claimed status through UNCHANGED (backward-compatible; no over-blocking).

Args:
    argv[1]  docs_path        docs repo root (may be empty → find_docs_root fallback)
    argv[2]  story_slug       the story slug ostler resolves
    argv[3]  claimed_status   apply-review's self-reported impl_result.status
    argv[4]  claimed_notes    apply-review's self-reported impl_result.notes

Stdlib-only: runs under the system python3. Shells out to the `ostler` CLI (same as
prepare-story.py). Outputs JSON: {"impl_result": {"status": "...", "notes": "..."}}
"""
from __future__ import annotations

import json
import subprocess
import sys

from workhorse.scriptutil import find_docs_root

RESOLUTION_FILE = "review-resolution.json"
SETTLEMENT_FILE = "review-settlement.json"


def _emit(status: str, notes: str) -> None:
    print(json.dumps({"impl_result": {"status": status, "notes": notes}}))


def main() -> None:
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    slug = sys.argv[2] if len(sys.argv) > 2 else ""
    claimed_status = (sys.argv[3] if len(sys.argv) > 3 else "") or "applied"
    claimed_notes = sys.argv[4] if len(sys.argv) > 4 else ""

    docs_root = find_docs_root(docs_path_arg)

    # Locate the structured verdict. Without one this gate is a pass-through so stories
    # that don't emit the sidecar (or non-Acme repos) keep the prior behavior.
    spec_dir = docs_root / "docs" / "specs" / slug
    resolution = spec_dir / RESOLUTION_FILE
    if not slug or not resolution.is_file():
        _emit(claimed_status, claimed_notes)
        return

    cmd = ["ostler", "-C", str(docs_root), "edit", "settle-review", slug, "--write"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()

    if proc.returncode != 0:
        # ostler hard-errored: a malformed verdict (no findings / unknown disposition) or
        # a missing story. Don't trust it — route back to re-apply (bounded by guard_review),
        # surfacing the reason rather than spinning on fabricated progress.
        reason = out or err or "ostler settle-review failed"
        _emit("needs_changes", f"review settlement FAILED: {reason}")
        return

    # ostler wrote the per-finding ledger. Branch on it: all verified → approve & exit,
    # any blocked → escalate that finding, otherwise some are still open → re-apply them.
    settlement = spec_dir / SETTLEMENT_FILE
    try:
        ledger = json.loads(settlement.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _emit("needs_changes", f"settlement ledger unreadable after settle-review ({exc})")
        return

    if ledger.get("any_blocked"):
        ids = ", ".join(ledger.get("blocked", [])) or "a finding"
        _emit("blocked", f"review settlement: {ids} reported unresolvable (blocked) — escalating.")
        return
    if ledger.get("all_verified"):
        ids = ", ".join(ledger.get("verified", [])) or "all findings"
        _emit("applied", f"review settlement: every finding verified against cited artifacts ({ids}).")
        return
    open_ids = ", ".join(f.get("id", "?") for f in ledger.get("open", []) if isinstance(f, dict)) or "some findings"
    _emit("needs_changes", f"review settlement: {open_ids} still open (proof missing/wrong) — re-applying.")


if __name__ == "__main__":
    main()
