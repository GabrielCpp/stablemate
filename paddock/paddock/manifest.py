"""A stat manifest of a tree, to prove a pass left it untouched."""

from __future__ import annotations

import os
from pathlib import Path

Manifest = dict[str, tuple[int, int, bool]]

IGNORED = (".paddock",)


def manifest(root: Path) -> Manifest:
    """`{relative path: (size, mtime_ns, is_symlink)}` for every entry under *root*."""
    found: Manifest = {}
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames[:] = sorted(name for name in dirnames if name not in IGNORED)
        for name in (*dirnames, *sorted(filenames)):
            if name in IGNORED:
                continue
            child = here / name
            info = child.lstat()
            found[child.relative_to(root).as_posix()] = (info.st_size, info.st_mtime_ns, child.is_symlink())
    return found


def diff_manifests(before: Manifest, after: Manifest) -> list[str]:
    """Human-readable lines naming what changed between two manifests."""
    changes: list[str] = []
    changes += [f"removed {name}" for name in sorted(set(before) - set(after))]
    changes += [f"added {name}" for name in sorted(set(after) - set(before))]
    changes += [
        f"modified {name}"
        for name in sorted(set(before) & set(after))
        if before[name] != after[name]
    ]
    return changes
