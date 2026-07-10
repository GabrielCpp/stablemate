"""Helpers for the workhorse integration.

A workhorse workflow bookends its agent work with two ``script`` nodes: one that
scans and leases a credential into ``.workhorse/credential.json``, and one that
releases the lease afterwards. These helpers own that file's shape.

The output file is the only artefact in saddlebag that contains a password, so
it is written with owner-only permissions and belongs under ``.workhorse/``,
which workhorse's default scaffolding gitignores.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from .models import AcquiredCredential

#: Where workhorse scaffolding expects run-scoped artefacts.
WORKHORSE_DIR = ".workhorse"


def write_credential(path: Path | str, acquired: AcquiredCredential) -> Path:
    """Serialise a leased credential to ``path`` with ``0600`` permissions.

    The mode is applied before the secret is written, so the password is never
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
        json.dump(acquired.to_dict(), handle, indent=2)
        handle.write("\n")
    return path


def read_credential(path: Path | str) -> dict[str, Any]:
    """Load a credential file written by :func:`write_credential`."""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def lease_id_of(path: Path | str) -> str:
    """The lease id inside a credential file — what ``release`` needs."""
    data = read_credential(path)
    lease_id = data.get("lease_id")
    if not lease_id:
        raise ValueError(f"{path} has no lease_id")
    return str(lease_id)
