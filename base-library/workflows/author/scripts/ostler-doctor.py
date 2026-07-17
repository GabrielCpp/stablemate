#!/usr/bin/env python3
"""Mechanical referential-integrity gate over the planning-doc graph (via the ostler API).

The surface-coverage gate relates authored work to the *feature set*; the per-epic coverage
validator proves seeds map to stories *within* an epic. Neither catches the **cross-run drift**
this gate does: a story referencing a seed that belongs to another epic, a knowledge path that
resolves to nothing — the "AI forgot what it created itself" class. `ostler.doctor()` computes (never asserts) the graph facts and reports these as
typed findings; this node turns its error-level findings into a blocking gate so they route to
the operator/resolver instead of shipping.

Design (matches the other deterministic gates here):
- **Opt-in by presence / fail-open on infra.** If the repo has no planning-doc graph, or the
  graph can't be loaded, the gate is a clean **skip** — it never blocks a run on tooling
  problems (mirrors build-inventory / verify-surface-coverage).
- **Errors block, warnings don't.** Only `severity == "error"` findings flip the gate to "no";
  `warn`-level (stale owners, schema nits) are surfaced in the report but never block.
- **Always exits 0.** Status is carried in the JSON output (`integrity_ok`), not the exit code —
  the script runner treats a non-zero exit as a hard ScriptExitError.

Output JSON:
    integrity_ok      : "yes" (clean) | "no" (error-level findings) | "skip" (not applicable)
    integrity_errors  : formatted, pointer-shaped list of error findings (empty unless "no")
    integrity_report  : one-line summary (org/profile/error+warn counts) for the run log

Args:
    argv[1]  epic_filter (optional) : restrict checks to one epic slug; empty → whole graph.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd().resolve()


def emit(ok: str, errors: str = "", report: str = "") -> NoReturn:
    print(json.dumps({
        "integrity_ok": ok,
        "integrity_errors": errors,
        "integrity_report": report,
    }))
    sys.exit(0)  # status is in the payload; a non-zero exit would hard-fail the node


def main(logger: logging.Logger) -> None:
    epic_filter = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    root = find_repo_root()
    okf = Ostler(root)

    try:
        report = okf.doctor(epic=epic_filter or None)
    except (OSError, ValueError, RuntimeError) as exc:
        logger.warning("ostler doctor could not run (%s) — skipped", exc)
        emit("skip", report=f"ostler doctor could not run ({exc}) — skipped")

    org = report.get("org", "?")
    profile = report.get("profile", "?")
    findings = report.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    summary = f"ostler doctor [{org}/{profile}]: {len(errors)} error(s), {len(warns)} warning(s)"
    logger.info(summary)

    if not errors:
        emit("yes", report=summary)

    # Pointer-shaped error list for the resolver: each line is code + scope + message.
    lines = [
        "ostler doctor found referential-integrity errors in the planning-doc graph.",
        "Each is a graph break (a reference that resolves to nothing, or to the wrong epic).",
        "Reconcile each with `ostler edit` (set-owner / relink / rename) or escalate — never",
        "delete a reference or fabricate an entity to silence the check.",
        "",
    ]
    for f in errors:
        scope = f.get("epic") or f.get("ref") or ""
        scope = f" ({scope})" if scope else ""
        lines.append(f"  - [{f.get('code', '?')}]{scope} {f.get('message', '')}")
    emit("no", errors="\n".join(lines), report=summary)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("ostler-doctor"))
