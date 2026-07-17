#!/usr/bin/env python3
"""Pick the next drainable item from the coder-filed backlog pool — FIX selection only.

The `## Filed by coder` heading in `docs/backlog.md` (populated exclusively by
`append-backlog-item.py`) is the fix loop's worklist. This script answers "is there
a fix to do, and which one" — it does not seed a story or touch the backlog file
itself (that's `seed-fix-story.py` / `prune-fix-item.py` / `mark-fix-blocked.py`).

Selection rule: the first bullet under `## Filed by coder` whose line does NOT
already contain `(blocked` (annotated by `mark-fix-blocked.py` after an exhausted
retry, so a permanently-stuck item is skipped on every later draw without being
removed from the backlog — it stays visible for a human).

Args: [docs_path] [backlog_path]
Outputs JSON: {"has_fix": "yes"|"no", "fix_bullet_id": "...", "fix_bullet_text": "...",
               "reason": "..."}
"""
from __future__ import annotations

import json
import logging
import re
import sys

from workhorse.scriptutil import find_docs_root

_FILED_HEADING = "## Filed by coder"
BACKLOG_ID_RE = re.compile(r"^\s*-\s*\[([A-Za-z0-9][A-Za-z0-9._-]*)\]\s*(.*)$")


def emit(**kwargs: str) -> None:
    payload = {"has_fix": "no", "fix_bullet_id": "", "fix_bullet_text": "", "reason": ""}
    payload.update(kwargs)
    print(json.dumps(payload))
    sys.exit(0)


def find_filed_section(lines: list[str]) -> list[str]:
    """Return the lines within the `## Filed by coder` section (exclusive of the
    heading, up to the next heading or EOF); empty if the section is absent."""
    for i, line in enumerate(lines):
        if line.strip() == _FILED_HEADING:
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("#"):
                j += 1
            return lines[i + 1:j]
    return []


def main(logger: logging.Logger) -> None:
    docs_path_arg = sys.argv[1] if len(sys.argv) > 1 else ""
    backlog_rel = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/backlog.md"

    root = find_docs_root(docs_path_arg)
    backlog_path = root / backlog_rel
    if not backlog_path.is_file():
        logger.info("no backlog file at %s — nothing to drain", backlog_rel)
        emit(reason=f"no backlog file at {backlog_rel} — nothing to drain")

    try:
        lines = backlog_path.read_text(encoding="utf-8").splitlines()
    except OSError as e:
        logger.warning("could not read %s: %s", backlog_rel, e)
        emit(reason=f"could not read {backlog_rel}: {e}")

    section = find_filed_section(lines)
    if not section:
        logger.info("no '%s' section — nothing to drain", _FILED_HEADING)
        emit(reason="no '## Filed by coder' section — nothing to drain")

    for line in section:
        m = BACKLOG_ID_RE.match(line)
        if not m:
            continue
        if "(blocked" in line:
            continue
        bid, text = m.group(1).strip(), m.group(2).strip()
        if not bid or not text:
            continue
        logger.info("drew '%s' from '%s'", bid, _FILED_HEADING)
        emit(has_fix="yes", fix_bullet_id=bid, fix_bullet_text=text,
             reason=f"drew '{bid}' from '{_FILED_HEADING}'")

    logger.info("'%s' has no drainable bullet (empty or all blocked)", _FILED_HEADING)
    emit(reason="'## Filed by coder' has no drainable bullet (empty or all blocked)")


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("select-next-fix-item"))
