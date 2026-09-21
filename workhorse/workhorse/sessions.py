"""Where a run keeps its agent-CLI session ids, and what a *chain* of turns is."""

from __future__ import annotations

import re
from pathlib import Path

SESSIONS_DIRNAME = ".sessions"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slug(key: str) -> str:
    """A chain key as a single safe filename."""
    return _UNSAFE.sub("-", key).strip("-") or "chain"


def chain_path(run_dir: Path, key: str) -> Path:
    """Where the session id for chain ``key`` is kept."""
    return run_dir / SESSIONS_DIRNAME / slug(key)


def read_chain(run_dir: Path, key: str) -> str:
    """The session id filed under ``key``, or ``""`` when that chain has not run yet."""
    if not key:
        return ""
    path = chain_path(run_dir, key)
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def run_dir_of(session_id_path: Path) -> Path:
    """The run directory a session file belongs to, chain file or not."""
    parent = session_id_path.parent
    return parent.parent if parent.name == SESSIONS_DIRNAME else parent
