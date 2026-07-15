#!/usr/bin/env python3
"""Invoke ``ostler qa context`` and always emit workflow routing JSON."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from qa_cli import emit, notes_for, run_ostler


def main() -> None:
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    story_file = sys.argv[2] if len(sys.argv) > 2 else ""
    features_root = sys.argv[3] if len(sys.argv) > 3 else ""
    source_roots_json = sys.argv[4] if len(sys.argv) > 4 else "[]"
    base = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else "HEAD"
    head = sys.argv[6] if len(sys.argv) > 6 and sys.argv[6] else "WORKTREE"
    docs_root = (
        Path(sys.argv[7]).resolve() if len(sys.argv) > 7 and sys.argv[7] else None
    )

    try:
        source_roots = json.loads(source_roots_json)
    except json.JSONDecodeError:
        source_roots = []

    args = ["qa", "context", "--base", base, "--head", head, "--spec", spec_dir]
    if features_root:
        args.extend(["--features-root", features_root])
    if story_file:
        args.extend(["--story-file", story_file])
    for source_root in source_roots if isinstance(source_roots, list) else []:
        if isinstance(source_root, str) and "=" in source_root:
            args.extend(["--source-root", source_root])
    args.append("--json")

    returncode, payload, stderr = run_ostler(args, cwd=docs_root)
    status = (
        "passed"
        if returncode == 0 and payload.get("status") != "invalid"
        else "invalid"
    )
    notes = notes_for(
        payload,
        stderr,
        "QA OKF context generated."
        if status == "passed"
        else "QA OKF context generation failed.",
    )
    emit("qa_context_build", status, notes, payload)


if __name__ == "__main__":
    main()
