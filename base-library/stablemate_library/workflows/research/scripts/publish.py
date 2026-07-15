#!/usr/bin/env python3
"""Commit and push the agent's spec/code edits to the result branch so they
survive the ephemeral container. Idempotent: a no-op commit is skipped.

Args:
    argv[1]  repo dir       (e.g. /workspace/<repo>)
    argv[2]  result branch  (e.g. <program-slug>/auto)
    argv[3]  program dir     (optional; for the commit-message label)

Outputs JSON: {"publish_result": {"pushed": true|false, "branch": "...", "status": "ok"}}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from workhorse.scriptutil import checkout, commit_all, push_to_origin, set_identity


def _emit(pushed: bool, branch: str, status: str = "ok") -> None:
    print(json.dumps({"publish_result": {"pushed": pushed, "branch": branch, "status": status}}))


def main() -> None:
    if len(sys.argv) < 2 or not sys.argv[1]:
        print("[publish] repo dir required", file=sys.stderr)
        sys.exit(1)
    repo_dir = sys.argv[1]
    result_branch = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "research/auto"
    program_dir = sys.argv[3] if len(sys.argv) > 3 else ""

    # Program label for the commit message, so a non-HRNet program is not mislabelled.
    # Prefer the program dir's basename (the proper, correctly-cased program name, e.g.
    # specs/SMCNv3 → SMCNv3); else derive from the result branch (drop trailing "/auto").
    if program_dir:
        program_label = Path(program_dir).name
    else:
        program_label = result_branch.rsplit("/", 1)[0] if "/" in result_branch else result_branch
    program_label = program_label or result_branch

    set_identity(repo_dir, "Research Agent", "research-agent@local")

    # Work on the result branch (create or reset to the current HEAD).
    checkout(repo_dir, result_branch, reset=True)

    if not commit_all(repo_dir, f"{program_label}: automated gate update"):
        print("[publish] no changes to commit", file=sys.stderr)
        _emit(False, result_branch)
        return

    if push_to_origin(repo_dir, result_branch, force_with_lease=True):
        _emit(True, result_branch)
    else:
        # No write credential / no remote: keep edits local; artifacts still capture them.
        print(f"[publish] push failed — edits remain on local branch {result_branch} only",
              file=sys.stderr)
        _emit(False, result_branch, status="push_failed")


if __name__ == "__main__":
    main()
