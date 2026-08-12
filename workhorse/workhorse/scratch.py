"""Scratch that belongs to a machine, not to a repo.

Some of what a run produces is neither a document nor a run artifact: a browser profile,
a cache a tool rebuilds, a log nobody reads twice. Written into the repo it is worse than
useless — okf-builder's shared browser parks tens of thousands of Chrome profile files
under the docs repo, and a coder run in the same checkout commits with ``git add -A``, so
one unlucky ordering puts the whole profile in every clone's history forever, where only
a rewrite removes it. That is not a hypothetical; it happened, and cost a rewrite.

So it goes to the stablemate cache instead, whose contract already says exactly the right
thing: *deletable at any time without loss*. Nothing here may be the only copy of
anything. A worklist a resume depends on is therefore NOT scratch and stays in the run's
`.agents/` directory — the test is whether losing it loses work.

**Why this lives in workhorse and not in a workflow.** The cache root reads
``$STABLEMATE_CACHE_DIR``, and a workflow may not read the environment (a value read
there is in no checkpoint and no telemetry, so a resume can silently take a different
one). The process boundary is where the environment belongs, and this module is on the
workhorse side of it: a workflow calls a function and gets a path.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from workhorse._vendor.stablemate_core.base_cache import cache_root

#: Everything below this is scratch. One parent so the whole lot is one `rm -rf`.
SCRATCH_DIRNAME = "scratch"

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _slug(subject: Path) -> str:
    """A readable, collision-free directory name for an absolute path.

    Readable because someone looking at the cache should be able to tell which checkout a
    directory belongs to; hashed because two checkouts of the same repo — a worktree, a
    clone under a different parent — have the same basename and must not share a browser
    profile. The name alone would collide; the digest alone would be unreadable.
    """
    resolved = Path(subject).resolve()
    name = _UNSAFE.sub("-", resolved.name).strip("-") or "root"
    digest = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:10]
    return f"{name}-{digest}"


def scratch_dir(kind: str, subject: Path | str) -> Path:
    """Create and return this machine's scratch directory for `kind` over `subject`.

    `kind` names the producer (``"okf-walkthrough"``), `subject` the checkout it is
    working on. The directory is created, because every caller wants it to exist and a
    cache the user deleted between two runs is the normal case, not an error.
    """
    path = cache_root() / SCRATCH_DIRNAME / kind / _slug(Path(subject))
    path.mkdir(parents=True, exist_ok=True)
    return path


__all__ = ["SCRATCH_DIRNAME", "scratch_dir"]
