#!/usr/bin/env python3
"""Remove a shipped fix's bullet from `docs/backlog.md` — backed by `okf.backlog_prune`.

`okf.backlog_prune(<id>)` already does exactly this (matches `- [<id>] ...` anywhere in the
file, regardless of section, and rewrites the file without it) — see `ostler/backlog.py`. This
script commands the OKF graph through the in-process `ostler` Python API (the library face of the
CLI) instead of shelling out, with a stdlib-only regex fallback for a custom `backlog_path` layout
ostler doesn't know to look at, so a mechanical removal it can do itself never hard-stops the fix
loop.

Args:
    argv[1]  bullet_id  : the backlog item id to remove (required)
    argv[2]  docs_path  : optional explicit docs root override (passed to find_docs_root)
    argv[3]  backlog_path : repo-relative backlog file (default docs/backlog.md)

Outputs JSON: {"pruned": "yes"|"no", "bullet_id": "...", "reason": "..."}
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import NoReturn

from ostler import Ostler
from workhorse.scriptutil import find_docs_root

BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")


def emit(**kwargs: str) -> NoReturn:
    payload = {"pruned": "no", "bullet_id": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def prune_via_regex(backlog_path: Path, bullet_id: str) -> bool:
    if not backlog_path.is_file():
        return False
    lines = backlog_path.read_text(encoding="utf-8").splitlines()
    kept, removed = [], False
    for line in lines:
        m = BACKLOG_ID_RE.match(line)
        if m and m.group(1).strip() == bullet_id:
            removed = True
            continue
        kept.append(line)
    if removed:
        backlog_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    return removed


def main() -> None:
    bullet_id = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else ""
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    backlog_rel = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "docs/backlog.md"

    if not bullet_id:
        emit(reason="no bullet_id supplied — nothing to prune")

    root = find_docs_root(docs_path_arg)
    okf = Ostler(root)

    if okf.backlog_prune(bullet_id).ok:
        emit(pruned="yes", bullet_id=bullet_id, reason=f"pruned '{bullet_id}' via ostler")

    # ostler reported no such item — still try the regex path in case the file layout
    # (e.g. a custom backlog_rel) is one ostler doesn't know to look at.
    removed = prune_via_regex(root / backlog_rel, bullet_id)
    if removed:
        emit(pruned="yes", bullet_id=bullet_id, reason=f"pruned '{bullet_id}' via direct edit")

    emit(bullet_id=bullet_id, reason=f"no backlog bullet '{bullet_id}' found to prune")


if __name__ == "__main__":
    main()
