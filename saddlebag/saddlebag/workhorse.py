"""Helpers for the workhorse integration.

Exactly one artefact leaves saddlebag carrying a secret: an environment rendered
by ``saddlebag env render``. It goes through :func:`write_private`, so it is
owner-only *before* it holds anything, and it lands wherever the environment's
target says — the repo's own already-gitignored ``.env`` path. There is no
credential file and no verb that emits a stored value: the vault is opaque, and
a workflow that needs a credential's *identity* gets it from the lease JSON that
``scan --select-via`` / ``acquire`` print, which never includes the password.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

#: Where workhorse scaffolding expects run-scoped artefacts.
WORKHORSE_DIR = ".workhorse"


def write_private(path: Path | str, text: str) -> Path:
    """Write ``text`` to ``path`` with ``0600`` permissions.

    The mode is applied before the secret is written, so the content is never
    momentarily world-readable. ``os.open``'s mode argument only takes effect when
    the file is *created*, so an ``fchmod`` follows it — otherwise overwriting an
    existing, permissive file would silently leave it group- and world-readable.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    owner_only = stat.S_IRUSR | stat.S_IWUSR
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, owner_only)
    os.fchmod(fd, owner_only)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path
