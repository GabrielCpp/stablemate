#!/usr/bin/env python3
"""Idempotently flag a fix bullet as blocked, in place, instead of pruning it.

Mirrors epic mode's `qa_give_up` "flag and continue" philosophy: a fix that still fails QA after
its one bounded retry is not deleted from the backlog (a human should still see it) and is not
retried forever (it would stall the drain loop) — it's annotated in place with
`(blocked: qa failed after retry)` so `select-next-fix-item.py` skips it on every future draw
while it stays visible in `docs/backlog.md`.

No `ostler` CLI command does this (only `add`/`prune`/`list` exist for backlog items), so this
edits the file directly using the same bullet-line contract as `append-backlog-item.py` /
`select-next-fix-item.py`.

Args:
    argv[1]  bullet_id  : the backlog item id to annotate (required)
    argv[2]  note       : the blocked-reason text (default "qa failed after retry")
    argv[3]  docs_path  : optional explicit docs root override (passed to find_docs_root)
    argv[4]  backlog_path : repo-relative backlog file (default docs/backlog.md)

Outputs JSON: {"marked": "yes"|"no", "bullet_id": "...", "reason": "..."}
"""
from __future__ import annotations

import json
import re
import sys

from workhorse.scriptutil import find_docs_root

BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")


def emit(**kwargs: str) -> None:
    payload = {"marked": "no", "bullet_id": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def main() -> None:
    bullet_id = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    note = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "qa failed after retry"
    docs_path_arg = sys.argv[3] if len(sys.argv) > 3 else ""
    backlog_rel = (sys.argv[4].strip() if len(sys.argv) > 4 and sys.argv[4] else "") or "docs/backlog.md"

    if not bullet_id:
        emit(reason="no bullet_id supplied — nothing to mark")

    root = find_docs_root(docs_path_arg)
    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        emit(bullet_id=bullet_id, reason=f"no backlog file at {backlog_rel}")

    lines = backlog_path.read_text(encoding="utf-8").splitlines()
    changed = False
    found = False
    for i, line in enumerate(lines):
        m = BACKLOG_ID_RE.match(line)
        if not m or m.group(1).strip() != bullet_id:
            continue
        found = True
        if "(blocked" in line:
            break  # already annotated — idempotent no-op
        lines[i] = f"{line.rstrip()} (blocked: {note})"
        changed = True
        break

    if not found:
        emit(bullet_id=bullet_id, reason=f"no backlog bullet '{bullet_id}' found to mark")

    if changed:
        backlog_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        emit(marked="yes", bullet_id=bullet_id, reason=f"marked '{bullet_id}' blocked: {note}")

    emit(marked="yes", bullet_id=bullet_id, reason=f"'{bullet_id}' already marked blocked (no-op)")


if __name__ == "__main__":
    main()
