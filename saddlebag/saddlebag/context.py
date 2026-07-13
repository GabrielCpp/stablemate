"""Ambient context inferred from where saddlebag is run.

A credential belongs to a *project*, and most of the time that project is simply
the repository you are standing in. Rather than make you retype ``--project`` on
every command, saddlebag infers it from the working directory and lets an explicit
flag override.
"""

from __future__ import annotations

from pathlib import Path


def infer_project(start: Path | str | None = None) -> str | None:
    """The project saddlebag operates in by default.

    Resolves to the name of the enclosing git repository — its top-level
    directory — so the answer is stable from any subdirectory of the repo.
    Outside a repository it falls back to the current directory's own name, and
    returns ``None`` only at the filesystem root.
    """
    path = (Path(start) if start is not None else Path.cwd()).resolve()
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            return parent.name or None
    return path.name or None
