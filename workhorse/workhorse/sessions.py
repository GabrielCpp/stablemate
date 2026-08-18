"""Where a run keeps its agent-CLI session ids, and what a *chain* of turns is.

The default contract is one clean context per node: ``<run_dir>/.session_id`` holds the
session the last turn used, and the ladder unlinks it before the next node so nobody
inherits a conversation they were not written for. A reviewer reading the author's
reasoning is not a reviewer.

A **chain** is the deliberate exception. A repair loop's laps are the same conversation:
lap two is told the same worklist as lap one and starts by re-deriving what lap one
already found, which costs a full turn of reading and hands the model a worse copy of
what it just had. Naming a chain — ``self.agent(..., session="docs-repair:STORY-1")`` —
files that lap's session id under ``<run_dir>/.sessions/<key>`` and asks the ladder to
resume it, so the laps are one conversation with one context to compact.

The key is per *worklist*, not per node: two stories repaired in one run must not share
a chain, or story two opens on story one's diff. Callers key on the story.

The layout is a module of its own because two layers build the same path from opposite
ends — the engine composes it from a run directory and a key, and
:func:`workhorse.runner.failure.record_session_map` has to recover the run directory
from a session file one level deeper than it used to be. A private convention in one of
them would silently write ``sessions.jsonl`` into ``.sessions/``.
"""

from __future__ import annotations

import re
from pathlib import Path

#: Chain files live here, under the run directory beside ``.session_id``.
SESSIONS_DIRNAME = ".sessions"

#: Everything outside this becomes a dash. A chain key carries a story id and a colon
#: (``qa-plan-repair:STORY-1``), which is a legal filename on Linux and not everywhere,
#: and a key is a name rather than a path — a ``/`` in one must not make a directory.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def slug(key: str) -> str:
    """A chain key as a single safe filename. Empty keys are refused by the caller."""
    return _UNSAFE.sub("-", key).strip("-") or "chain"


#: What an agent CLI mints. Every backend this runner drives hands back a UUID, and a
#: chain key is a human-written name (``qa-plan-repair:STORY-1``) that cannot collide
#: with one — which is what lets a single ``session=`` parameter carry either.
_SESSION_ID = re.compile(r"\A[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")


def is_session_id(value: str) -> bool:
    """Whether ``value`` is a literal session id rather than a chain key.

    A caller that already holds an id — from checkpointed state, or from an operator
    naming a conversation to resume — passes it where a key would go, and the id becomes
    the key: a chain named after itself, seeded with itself, resumed like any other.
    """
    return bool(_SESSION_ID.match(value.strip()))


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
    """The run directory a session file belongs to, chain file or not.

    ``sessions.jsonl``, the turn-visit counter and the transcripts are per *run*, not
    per chain, so everything that writes them has to land one level up from a chain
    file and in place for ``.session_id``.
    """
    parent = session_id_path.parent
    return parent.parent if parent.name == SESSIONS_DIRNAME else parent
