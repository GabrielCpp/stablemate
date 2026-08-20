"""Zip a repository state, and put it back exactly as it was.

`shutil.make_archive` is not enough for what a seed has to carry. A seed is a whole
repo including `.git`, and three of its properties die in a naive zip:

* **the executable bit** — `.git/hooks/*` and every checked-in script stop being
  runnable, which makes an unpacked seed behave differently from the tree it was
  captured from and says nothing about why;
* **symlinks** — followed and duplicated as regular files, which silently doubles a
  `node_modules`-shaped tree and turns a relative link into a stale copy;
* **reproducibility** — a zip carrying each file's mtime hashes differently every
  capture, so the sha256 in the pointer would stop being a statement about the
  *content*.

So entries are written sorted, at a fixed timestamp, with the mode preserved in
`external_attr` — the format zipfile already reads back, just not one it writes by
default.
"""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

#: A fixed DOS timestamp for every entry. 1980-01-01 is the earliest the zip format can
#: represent; any constant would do, and the point is only that it is a constant — see
#: the reproducibility note above.
FIXED_TIME = (1980, 1, 1, 0, 0, 0)

#: Directory names that are build output or a local environment, refused at capture
#: anywhere in the tree. Hand-zipping is what lets a `.venv` into a fixture — with its
#: absolute interpreter paths, its compiled extensions and its hundreds of megabytes —
#: and `seed capture` is the contract's one enforcement point.
JUNK_ANYWHERE = (
    ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".gradle", ".next", ".turbo", ".parcel-cache",
)

#: Refused at the repo root only. `build/` and `dist/` are the conventional output
#: directories there, and ordinary source directories anywhere else — `docs/build` is a
#: real thing to want in a seed.
JUNK_AT_ROOT = ("build", "dist", "target", "out")

#: Never captured, junk-scan or not: it is this tool's own work area, and a seed
#: captured from a repo that has run paddock would otherwise carry a copy of every
#: result it ever staged.
ALWAYS_EXCLUDED = (".paddock",)


class ArchiveError(RuntimeError):
    """A tree that cannot be captured, or an archive that cannot be trusted."""


@dataclass(frozen=True, slots=True)
class Entry:
    """One member of the archive, named relative to the archive root."""

    arcname: str
    path: Path
    is_dir: bool
    is_symlink: bool


def _excluded(rel: Path, excludes: Sequence[str]) -> bool:
    posix = rel.as_posix()
    return any(
        fnmatch(posix, pattern) or any(fnmatch(part, pattern) for part in rel.parts)
        for pattern in (*excludes, *ALWAYS_EXCLUDED)
    )


def junk_in(root: Path, excludes: Sequence[str] = ()) -> list[str]:
    """Every build-output or local-environment directory the tree still carries.

    Returned rather than raised so the caller can name all of them at once: a capture
    that dies on the first `.venv` and then on `node_modules` is two round trips through
    a multi-gigabyte walk.
    """
    found: list[str] = []
    for entry in walk(root, excludes):
        if not entry.is_dir:
            continue
        rel = Path(entry.arcname)
        name = rel.name
        if name in JUNK_ANYWHERE or (len(rel.parts) == 1 and name in JUNK_AT_ROOT):
            found.append(entry.arcname)
    return sorted(found)


def walk(root: Path, excludes: Sequence[str] = ()) -> Iterator[Entry]:
    """Every file, directory and symlink under *root*, depth-first and sorted.

    Directories are yielded too, and not only for the empty ones: a QA lane's `qa/`
    output directory is part of the state a seed captures even when the run that made it
    left nothing in it, and a zip of files alone silently drops it.

    Symlinks are yielded as symlinks and never descended into — following one is how a
    capture leaves the tree it was pointed at.
    """
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        dirnames.sort()
        kept: list[str] = []
        for name in dirnames:
            rel = (here / name).relative_to(root)
            if _excluded(rel, excludes):
                continue
            child = here / name
            if child.is_symlink():
                # A symlinked directory is an entry, not a subtree to walk.
                yield Entry(rel.as_posix(), child, is_dir=False, is_symlink=True)
                continue
            kept.append(name)
            yield Entry(rel.as_posix(), child, is_dir=True, is_symlink=False)
        dirnames[:] = kept
        for name in sorted(filenames):
            child = here / name
            rel = child.relative_to(root)
            if _excluded(rel, excludes):
                continue
            yield Entry(rel.as_posix(), child, is_dir=False, is_symlink=child.is_symlink())


def create(root: Path, dest: Path, *, prefix: str, excludes: Sequence[str] = ()) -> Path:
    """Zip *root* into *dest*, with every entry under `prefix/`.

    The prefix is the directory name the tree unpacks back into, and it is load-bearing
    rather than cosmetic: farrier derives the names of the files it generates from the
    repo directory's basename, so a tree unpacked under a different name gets a fresh set
    of generated skills while the tracked ones the book points at dangle.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    draft = dest.with_name(dest.name + ".part")
    entries = sorted(walk(root, excludes), key=lambda e: e.arcname)
    with zipfile.ZipFile(draft, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            _write(archive, entry, prefix)
    draft.replace(dest)
    return dest


def _write(archive: zipfile.ZipFile, entry: Entry, prefix: str) -> None:
    arcname = f"{prefix}/{entry.arcname}" + ("/" if entry.is_dir else "")
    info = zipfile.ZipInfo(arcname, date_time=FIXED_TIME)
    if entry.is_symlink:
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, os.readlink(entry.path))
        return
    mode = entry.path.lstat().st_mode
    info.external_attr = (stat.S_IMODE(mode) | (stat.S_IFDIR if entry.is_dir else stat.S_IFREG)) << 16
    if entry.is_dir:
        info.external_attr |= 0x10  # the MS-DOS directory flag, which unzip(1) reads
        archive.writestr(info, b"")
        return
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, entry.path.read_bytes())


def extract(zip_path: Path, dest: Path) -> Path:
    """Unpack *zip_path* under *dest*, restoring modes and symlinks.

    Every member is checked to land inside *dest* before anything is written. A zip is
    outside data — a seed can arrive over HTTPS from a bucket nobody in this repo
    controls — and `..` in a member name is the oldest way an archive writes to a path
    the extractor never intended.
    """
    dest.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(resolved_dest):
                raise ArchiveError(
                    f"{zip_path}: member {info.filename!r} escapes the extraction directory"
                )
            _restore(archive, info, target)
    return dest


def _restore(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    mode = info.external_attr >> 16
    if stat.S_ISLNK(mode):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.unlink(missing_ok=True)
        target.symlink_to(archive.read(info).decode("utf-8"))
        return
    if info.is_dir():
        target.mkdir(parents=True, exist_ok=True)
        if stat.S_IMODE(mode):
            target.chmod(stat.S_IMODE(mode))
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(archive.read(info))
    if stat.S_IMODE(mode):
        target.chmod(stat.S_IMODE(mode))


def digest(path: Path) -> str:
    """The sha256 of a file, read in blocks — a seed zip is routinely hundreds of MiB."""
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def manifest(root: Path) -> dict[str, tuple[int, int, bool]]:
    """`{relative path: (size, mtime_ns, is_symlink)}` for every entry under *root*.

    What "`score` is read-only over the result" is checked with. Not a content hash: the
    tree is a whole repo including `.git` and the check runs on every scored task, so it
    has to cost a stat per file rather than a read. Any write a score function makes
    moves an mtime, which is what the guard is looking for — a rewrite that restores the
    byte-identical content it found is not a mutation this needs to catch.
    """
    found: dict[str, tuple[int, int, bool]] = {}
    for entry in walk(root):
        info = entry.path.lstat()
        found[entry.arcname] = (info.st_size, info.st_mtime_ns, entry.is_symlink)
    return found


def diff_manifests(
    before: dict[str, tuple[int, int, bool]], after: dict[str, tuple[int, int, bool]]
) -> list[str]:
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


def total_size(entries: Iterable[Entry]) -> int:
    return sum(
        entry.path.lstat().st_size for entry in entries if not entry.is_dir and not entry.is_symlink
    )
