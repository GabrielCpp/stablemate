"""Where the repositories of the workspace a book belongs to sit on disk."""

from __future__ import annotations

from pathlib import Path

from ostler._vendor.stablemate_core import books


def checkout(name: str) -> str:
    """The folder of the workspace member `name`, for a stack or a process that builds from it."""
    members = books.book_checkouts(Path.cwd())
    if name not in members:
        known = ", ".join(sorted(members)) or "none"
        raise LookupError(f"no workspace member {name!r}; known members: {known}")
    return str(members[name])
