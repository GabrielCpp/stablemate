#!/usr/bin/env python3
"""Write-time reconciliation gate: flag **scope this run silently dropped** vs the git baseline.

`ostler doctor` catches *dangling* references; it does NOT catch a **clean removal** — an IDed
entity (a seed item, a story) deleted along with every reference to it. That is the "dropped
scope" / "AI forgot what it created itself" failure: a re-run re-derives an epic and quietly omits
a seed item a prior run committed, leaving no dangling ref for doctor to find. This gate compares
the current planning-doc graph against the **last committed** version and reports every baseline
entity that is now gone, so the operator confirms it was an intentional drop (recorded) rather
than silent regression.

Under the OKF model an epic's seeds and story-DAG fold into its ``epic.md`` (``## Seeds`` →
``### <seed-id>``; ``## Stories`` → ``### <slug>``) — there is no ``seed.json`` /
``dependencies.json``. So this compares the parsed ``epic.md`` subsection ids on both sides.

Design (matches the other deterministic gates):
- **Removals block, additions don't.** Only entities present in the baseline and absent now are
  flagged; new epics/seeds/stories this run adds are ignored.
- **Fail-open on infra.** Not a git repo, git missing, or an epic with no committed baseline (a
  brand-new epic) → clean **skip** for that scope.
- **Always exits 0.** Status is in the JSON output, not the exit code.

Output JSON:
    reconcile_ok      : "yes" | "no" | "skip"
    reconcile_errors  : pointer-shaped list of dropped entities (empty unless "no")
    reconcile_report  : one-line summary

Args:
    argv[1]  epics_dir (default docs/epics) : repo-relative epics root.
    argv[2]  baseline ref (default HEAD)     : git ref to compare against.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_H2_RE = re.compile(r"^##\s+(.*\S)\s*$")
_H3_RE = re.compile(r"^###\s+(.*\S)\s*$")


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    return Path(env_root).resolve() if env_root else Path.cwd().resolve()


def emit(ok: str, errors: str = "", report: str = "") -> None:
    print(json.dumps({"reconcile_ok": ok, "reconcile_errors": errors, "reconcile_report": report}))
    sys.exit(0)


def git_show(root: Path, ref: str, relpath: str) -> str | None:
    """Return the file's content at `ref`, or None if it didn't exist there / git is unavailable."""
    try:
        proc = subprocess.run(["git", "-C", str(root), "show", f"{ref}:{relpath}"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def subsection_ids(text: str, heading: str) -> set[str]:
    """The ``### <id>`` titles directly under the ``## <heading>`` section of an epic.md body."""
    ids: set[str] = set()
    in_section = False
    for line in (text or "").splitlines():
        h2 = _H2_RE.match(line)
        if h2:
            in_section = h2.group(1).strip().lower() == heading.lower()
            continue
        if in_section:
            h3 = _H3_RE.match(line)
            if h3:
                ids.add(h3.group(1).strip())
    return ids


def main() -> None:
    epics_rel = (sys.argv[1].strip() if len(sys.argv) > 1 else "") or "docs/epics"
    ref = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or "HEAD"
    root = find_repo_root()
    epics_dir = root / epics_rel

    # Fail-open: no git, or detached/empty repo with no resolvable baseline → skip.
    if git_show(root, ref, epics_rel) is None and not (root / ".git").exists():
        emit("skip", report="not a git repo — reconciliation gate skipped")
    if not epics_dir.is_dir():
        emit("skip", report=f"no epics dir at {epics_rel} — skipped")

    drops: list[str] = []
    checked = 0
    for epic_md in sorted(epics_dir.glob("*/epic.md")):
        epic = epic_md.parent.name
        rel = str(epic_md.relative_to(root))
        base = git_show(root, ref, rel)
        if base is None:
            continue  # brand-new epic (no committed baseline) — nothing to reconcile
        checked += 1
        now = epic_md.read_text(encoding="utf-8")

        gone_seeds = subsection_ids(base, "Seeds") - subsection_ids(now, "Seeds")
        for sid in sorted(gone_seeds):
            drops.append(f"  - [dropped-seed] ({epic}) seed item '{sid}' was committed but is "
                         f"absent now — confirm it was intentionally dropped (record the reason), "
                         f"or restore it")

        gone_stories = subsection_ids(base, "Stories") - subsection_ids(now, "Stories")
        for slug in sorted(gone_stories):
            drops.append(f"  - [dropped-story] ({epic}) story '{slug}' was committed but is "
                         f"absent now — confirm intentional, or restore it")

    if checked == 0:
        emit("skip", report=f"no epics with a committed baseline at {ref} — skipped")
    summary = f"reconcile vs {ref}: {checked} epic(s) checked, {len(drops)} silent drop(s)"
    if not drops:
        emit("yes", report=summary)
    lines = [
        "This run silently removed planning entities that a prior run committed.",
        "Each is a scope drop with no dangling reference left for `ostler doctor` to catch.",
        "Confirm each was intentional (record the disposition/reason) or restore it — a silent",
        "removal of prior scope is a regression, not a clean re-derivation.",
        "",
        *drops,
    ]
    emit("no", errors="\n".join(lines), report=summary)


if __name__ == "__main__":
    main()
