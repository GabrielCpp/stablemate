#!/usr/bin/env python3
"""Append-only **attempts ledger** for a bounded rework loop (Arbor HTR, file-native).

A bounded rework loop today carries only the *latest* failure into the next attempt, so the
reworker can re-try an approach that already failed two cycles ago — the loop spins without
accumulating. This records each attempt's failure as a durable, tracked markdown file so the
next rework reads the **negative constraints** ("these approaches already failed — don't repeat
them"), exactly the structured-memory idea from Arbor's Hypothesis Tree Refinement, but as a plain
git-tracked artifact (no store, no service).

It appends one entry per attempt and emits the full ledger so the rework prompt can read it.
**Idempotent**: re-running with the same ``label`` (e.g. a resumed node) does not duplicate the
entry. Never fails the run — a write problem degrades to an empty ``prior_attempts``.

Stdlib-only: runs under the system ``python3``, not the uv venv.

Args:
    argv[1]  ledger_path : repo-relative ledger file (e.g. <story_dir>/attempts.md)
    argv[2]  label        : this attempt's label (e.g. the rework count) — heading + dedupe key
    argv[3]  note         : why this attempt failed (validator errors / audit refutation)

Outputs JSON: {"prior_attempts": "<full ledger markdown>", "ledger": "<repo-relative path>"}
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(prior: str, ledger_rel: str) -> None:
    print(json.dumps({"prior_attempts": prior, "ledger": ledger_rel}))
    sys.exit(0)


def main() -> None:
    ledger_rel = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    label = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "?"
    note = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "(no detail recorded)"

    if not ledger_rel:
        emit("", "")

    root = find_repo_root()
    path = root / ledger_rel
    heading = f"## Attempt {label}"

    try:
        existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        existing = ""

    # Idempotent: a resumed node re-running the same attempt must not duplicate the entry.
    if heading in existing:
        emit(existing.strip(), ledger_rel)

    if not existing.strip():
        existing = "# Attempts ledger\n\nEach entry is an approach that FAILED — do not repeat it.\n"

    entry = f"\n{heading}\nFailed: {note}\n"
    updated = existing.rstrip() + "\n" + entry

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")
    except OSError:
        # Never fail the run on a ledger write problem — degrade to whatever we could read.
        emit(existing.strip(), ledger_rel)

    emit(updated.strip(), ledger_rel)


if __name__ == "__main__":
    main()
