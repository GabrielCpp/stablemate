#!/usr/bin/env python3
"""okf-builder: accept the code-fix-only a11y defects that stall the fixup loop — with an IOU.

Reached only from ``guard_fixup_progress``, i.e. after the doctor→fixup→doctor loop has stalled:
the identical finding set recurred for N rounds because its repair cannot land in the book. A few
doctor findings are genuinely **code-fix-only** — two controls that co-render with one accessible
name (``ambiguous-locator``), an operable control the source leaves unnamed (``unnamed-interactive``).
Documentation cannot resolve them, and re-flagging them forever is not convergence.

This node accepts each such defect the honest way, never by hiding it:
  * a **doctor waiver** (``docs/doctor-waivers.json``) downgrades the finding error→warn — it stays
    visible in ``doctor --json`` with its reason, it just stops gating; and
  * a **backlog IOU** names the real fix, asks for the waiver to be removed once done, and gives the
    exact command to re-run and confirm the book is green *without* the waiver.

A stalled finding that is NOT auto-waivable (a mis-annotated role, a missing bullet — things a doc
edit *could* fix) is a genuine dead end: emit ``has_unwaivable=yes`` and let the workflow route to
the honest ``doctor_stuck`` terminal rather than paper over it.

Args: [repo_root] [features_root] [service]
Outputs JSON: {"has_unwaivable","waived_count","note"}
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Doctor codes whose ONLY real remedy is a source change. Deliberately narrow: a code a doc edit
# could fix must keep failing until it is actually fixed, never be auto-accepted.
AUTO_WAIVABLE = frozenset({"ambiguous-locator", "unnamed-interactive"})

_BACKLOG_SECTION = "Accessibility — waived defects to fix in code"


def emit(**kw: object) -> None:
    payload: dict[str, object] = {"has_unwaivable": "no", "waived_count": 0, "note": ""}
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _scoped_error_findings(doctor_report: dict, repo_root: str, features: str) -> list[dict]:
    """Error-severity findings located in the service book (mirrors checkpoint._doctor_for_features).

    Already-waived findings are ``warn`` and so excluded — re-running this node never re-waives them.
    """
    try:
        prefix = Path(features).resolve().relative_to(Path(repo_root).resolve()).as_posix().rstrip("/")
    except ValueError:
        prefix = Path(features).as_posix().rstrip("/")
    out = []
    for finding in doctor_report.get("findings", []):
        if not isinstance(finding, dict) or finding.get("severity") != "error":
            continue
        path = str(finding.get("path", ""))
        if not prefix or path == prefix or path.startswith(prefix + "/"):
            out.append(finding)
    return out


def main(logger: logging.Logger) -> None:
    repo_root = sys.argv[1] if len(sys.argv) > 1 else "."
    features = sys.argv[2] if len(sys.argv) > 2 else ""
    service = sys.argv[3] if len(sys.argv) > 3 else ""

    try:
        from ostler import Ostler, backlog as backlog_mod
    except ImportError as exc:  # ostler must be importable in workhorse's env to waive
        logger.error("ostler unavailable — cannot waive: %s", exc)
        emit(has_unwaivable="yes", note=f"ostler import failed: {exc}")

    okf = Ostler(repo_root)
    findings = _scoped_error_findings(okf.doctor(), repo_root, features)
    if not findings:
        # Nothing standing (a race, or all already waived): let the next checkpoint converge.
        emit(note="no standing error findings — nothing to waive")

    unwaivable = [f for f in findings if f.get("code") not in AUTO_WAIVABLE]
    if unwaivable:
        for f in unwaivable:
            logger.warning("doctor stuck — not auto-waivable: %s %s: %s",
                           f.get("code"), f.get("ref"), str(f.get("message", ""))[:200])
        emit(has_unwaivable="yes",
             note=f"{len(unwaivable)} standing finding(s) are not auto-waivable "
                  f"({', '.join(sorted({str(f.get('code')) for f in unwaivable}))}) — routing to doctor_stuck")

    reissue = (f"workhorse run okf-builder --params '{{\"service\":\"{service}\","
               f"\"recheck_only\":\"yes\"}}'")
    waived = 0
    for f in findings:
        code, ref = str(f.get("code", "")), str(f.get("ref", ""))
        # An ostler-minted, repo-prefixed id (PRED-15) — a first-class numbered work item, not a
        # descriptive slug. Each error finding is numbered exactly once: once waived it becomes a
        # `warn` and is excluded from the error set above, so a re-run never re-mints for it.
        bid = okf.allocate_id()
        okf.add_doctor_waiver(
            code, ref,
            f"code-fix-only a11y defect auto-waived after the doc-repair loop stalled; "
            f"tracked by backlog [{bid}]", bid)
        remedy = str(f.get("suggestion", "") or "give the control a distinct accessible name")
        text = (f"BUG(a11y/{code}): {ref} — {str(f.get('message', ''))[:220]} "
                f"Fix in source ({remedy}), then remove this finding's entry from "
                f"docs/doctor-waivers.json and re-run `{reissue}` to confirm doctor is green "
                f"without the waiver.")
        # Use the cached graph directly (backlog.add re-reads docs/backlog.md itself, so dedup still
        # sees earlier adds) — the facade's backlog_add would reload the whole book per call.
        backlog_mod.add(okf.graph, bid, text, section=_BACKLOG_SECTION)
        waived += 1
        logger.info("waived %s %s + filed backlog [%s]", code, ref, bid)

    emit(waived_count=waived,
         note=f"auto-waived {waived} code-fix-only a11y defect(s); backlog IOUs filed under "
              f"'{_BACKLOG_SECTION}'")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("auto-waive"))
