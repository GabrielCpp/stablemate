#!/usr/bin/env python3
"""Mechanical referential-integrity gate over the planning-doc graph (via `ostler doctor`).

The surface-coverage gate relates authored work to the *feature set*; the per-epic coverage
validator proves seeds map to stories *within* an epic. Neither catches the **cross-run drift**
this gate does: a knowledge gap owned by a story that no longer exists, a story referencing a
seed that belongs to another epic, a dangling `[gap:…]` tag — the "AI forgot what it created
itself" class. `ostler doctor` computes (never asserts) the graph facts and reports these as
typed findings; this node turns its error-level findings into a blocking gate so they route to
the operator/resolver instead of shipping.

Design (matches the other deterministic gates here):
- **Opt-in by presence / fail-open on infra.** If `ostler` is not installed, or the repo has no
  planning-doc graph, or doctor's output can't be parsed, the gate is a clean **skip** — it never
  blocks a run on tooling problems (mirrors build-inventory / verify-surface-coverage).
- **Errors block, warnings don't.** Only `severity == "error"` findings flip the gate to "no";
  `warn`-level (stale owners, schema nits) are surfaced in the report but never block.
- **Always exits 0.** Status is carried in the JSON output (`integrity_ok`), not the exit code —
  the script runner treats a non-zero exit as a hard ScriptExitError. `ostler`'s own non-zero
  exit on findings is captured and ignored.

Output JSON:
    integrity_ok      : "yes" (clean) | "no" (error-level findings) | "skip" (not applicable)
    integrity_errors  : formatted, pointer-shaped list of error findings (empty unless "no")
    integrity_report  : one-line summary (org/profile/error+warn counts) for the run log

Args:
    argv[1]  epic_filter (optional) : restrict checks to one epic slug; empty → whole graph.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    return Path.cwd().resolve()


def emit(ok: str, errors: str = "", report: str = "") -> None:
    print(json.dumps({
        "integrity_ok": ok,
        "integrity_errors": errors,
        "integrity_report": report,
    }))
    sys.exit(0)  # status is in the payload; a non-zero exit would hard-fail the node


def main() -> None:
    epic_filter = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    root = find_repo_root()

    ostler = shutil.which("ostler")
    if not ostler:
        emit("skip", report="ostler not installed — integrity gate skipped")

    cmd = [ostler, "doctor", "--json"]
    if epic_filter:
        cmd += ["--epic", epic_filter]
    try:
        proc = subprocess.run(cmd, cwd=str(root), capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        emit("skip", report=f"ostler doctor could not run ({exc}) — skipped")

    # ostler exits non-zero when it finds breaks; that's expected — parse stdout regardless.
    raw = proc.stdout or ""
    start = raw.find("{")
    if start == -1:
        emit("skip", report="ostler doctor produced no JSON — skipped")
    try:
        report = json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
        emit("skip", report="ostler doctor output was not parseable JSON — skipped")

    org = report.get("org", "?")
    profile = report.get("profile", "?")
    findings = report.get("findings", [])
    errors = [f for f in findings if f.get("severity") == "error"]
    warns = [f for f in findings if f.get("severity") == "warn"]
    summary = f"ostler doctor [{org}/{profile}]: {len(errors)} error(s), {len(warns)} warning(s)"

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
    main()
