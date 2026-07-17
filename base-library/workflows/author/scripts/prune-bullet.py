#!/usr/bin/env python3
"""Prune ONE consumed `- [id] …` bullet from the backlog (author story mode tail).

After story mode authors a single story, this removes just the one backlog bullet it
consumed — but only when the bullet actually came from the backlog (``from_backlog`` ==
"yes"); a literal/inline bullet has nothing to prune. This keeps the backlog a live
worklist, the same way ``prune-backlog.py`` does for a fully-authored epic, without
touching any other epic's bullets.

Best-effort and idempotent: matches the `- [<bullet_id>]` line by id; a missing backlog,
absent id, or write failure is swallowed so the run never dies over a tidy-up.

Stdlib-only: scripts run under the system ``python3``, not the uv venv.

Args:
    argv[1]  backlog       : repo-relative backlog markdown path (default docs/backlog.md)
    argv[2]  bullet_id      : the `[id]` to remove
    argv[3]  from_backlog   : "yes" to prune, anything else is a no-op

Outputs JSON: {"backlog_pruned": {"removed": <n>, "remaining": <n>}}
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]")
_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def emit(removed: int, remaining: int) -> None:
    print(json.dumps({"backlog_pruned": {"removed": removed, "remaining": remaining}}))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    backlog_rel = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/backlog.md"
    bullet_id = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    from_backlog = sys.argv[3].strip().lower() if len(sys.argv) > 3 and sys.argv[3] else ""

    if from_backlog != "yes" or not bullet_id:
        logger.info("bullet '%s' is not from the backlog (or missing) — no-op", bullet_id)
        emit(0, 0)  # inline bullet (or nothing to prune): no-op

    root = find_repo_root()
    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        logger.info("no backlog at %s — nothing to prune", backlog_path)
        emit(0, 0)

    try:
        lines = backlog_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        logger.warning("could not read backlog %s — nothing to prune", backlog_path)
        emit(0, 0)

    kept: list[str] = []
    removed = 0
    remaining_bullets = 0
    for line in lines:
        m = BACKLOG_ID_RE.match(line)
        if m and m.group(1).strip() == bullet_id:
            removed += 1
            continue
        if _BULLET_RE.match(line):
            remaining_bullets += 1
        kept.append(line)

    if removed:
        try:
            backlog_path.write_text("".join(kept), encoding="utf-8")
        except OSError:
            logger.warning("could not write pruned backlog %s — best-effort, continuing", backlog_path)

    logger.info("pruned bullet '%s' from %s (removed=%d, remaining=%d)",
                bullet_id, backlog_rel, removed, remaining_bullets)
    emit(removed, remaining_bullets)


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("prune-bullet"))
