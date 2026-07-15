#!/usr/bin/env python3
"""Prune a fully-authored epic's consumed bullets from the backlog — ostler-backed.

Called once an epic passes coverage validation (it is fully authored into stories). Reads the
epic's seeds from its ``epic.md`` (``ostler list --type seed --epic <epic>``) — each seed records
the verbatim ``sourceBullet`` it came from — and removes the matching lines from the backlog
markdown, so the backlog stays a live worklist that shrinks as work is authored (mirrors how coder
prunes finished epics from the epics index).

Best-effort and idempotent: matching is tolerant (a backlog line is dropped when its bullet text
equals, contains, or is contained by a ``sourceBullet``, min length 8); unmatched bullets are left
in place; a failure to write is swallowed so the run never dies just because the backlog couldn't
be tidied. The backlog is ostler-managed markdown but plain-text, so it is rewritten in place.

Stdlib-only except for shelling out to the globally-installed ``ostler`` CLI.

Args:
    argv[1]  backlog  : repo-relative path to the backlog markdown
    argv[2]  epic_dir : repo-relative epic folder (docs/epics/<epic>)

Outputs JSON: {"backlog_pruned": {"removed": <n>, "remaining": <n>}}
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (
            candidate / "docs" / "epics"
        ).is_dir():
            return candidate
    return here


def ostler_json(root: Path, args: list[str], opener: str):
    ostler = shutil.which("ostler")
    if not ostler:
        return None
    try:
        proc = subprocess.run(
            [ostler, *args], cwd=str(root), capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None
    raw = (proc.stdout or "").strip()
    start = raw.find(opener)
    if start == -1:
        return [] if opener == "[" else None
    try:
        return json.JSONDecoder().raw_decode(raw[start:])[0]
    except (json.JSONDecodeError, ValueError):
        return None


def normalize(line: str) -> str:
    """Strip a leading bullet/number marker and surrounding whitespace, lowercased."""
    return _BULLET_RE.sub("", line).strip().lower()


def matches(backlog_norm: str, seed_norms: list[str]) -> bool:
    if not backlog_norm:
        return False
    for sn in seed_norms:
        if not sn:
            continue
        if backlog_norm == sn:
            return True
        if (
            len(backlog_norm) >= 8
            and len(sn) >= 8
            and (backlog_norm in sn or sn in backlog_norm)
        ):
            return True
    return False


def emit(removed: int, remaining: int) -> NoReturn:
    print(json.dumps({"backlog_pruned": {"removed": removed, "remaining": remaining}}))
    sys.exit(0)


def main() -> None:
    backlog_rel = (
        sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "docs/backlog.md"
    )
    epic_dir_rel = sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else ""
    root = find_repo_root()
    backlog_path = root / backlog_rel
    epic = Path(epic_dir_rel).name if epic_dir_rel else ""

    if not backlog_path.is_file() or not epic:
        emit(0, 0)

    seeds = (
        ostler_json(root, ["list", "--type", "seed", "--epic", epic, "--json"], "[")
        or []
    )
    seed_norms = [normalize(str(s.get("sourceBullet", ""))) for s in seeds]
    seed_norms = [s for s in seed_norms if s]
    if not seed_norms:
        emit(0, 0)

    try:
        lines = backlog_path.read_text(encoding="utf-8").splitlines(keepends=True)
    except OSError:
        emit(0, 0)

    kept: list[str] = []
    removed = 0
    remaining_bullets = 0
    for line in lines:
        is_bullet = bool(_BULLET_RE.match(line))
        if is_bullet and matches(normalize(line), seed_norms):
            removed += 1
            continue
        if is_bullet:
            remaining_bullets += 1
        kept.append(line)

    if removed:
        try:
            backlog_path.write_text("".join(kept), encoding="utf-8")
        except OSError:
            pass  # best-effort: never fail the run over a tidy-up write

    emit(removed, remaining_bullets)


if __name__ == "__main__":
    main()
