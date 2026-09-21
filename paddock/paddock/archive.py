"""Zip a repository state, and put it back exactly as it was."""

from __future__ import annotations

import hashlib
import os
import stat
import zipfile
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

FIXED_TIME = (1980, 1, 1, 0, 0, 0)

JUNK_ANYWHERE = (
    ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".gradle", ".next", ".turbo", ".parcel-cache",
)

JUNK_AT_ROOT = ("build", "dist", "target", "out")

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
    """Every build-output or local-environment directory the tree still carries."""
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
    """Every file, directory and symlink under *root*, depth-first and sorted."""
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
    """Zip *root* into *dest*, with every entry under `prefix/`."""
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
        info.external_attr |= 0x10
        archive.writestr(info, b"")
        return
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, entry.path.read_bytes())


def extract(zip_path: Path, dest: Path) -> Path:
    """Unpack *zip_path* under *dest*, restoring modes and symlinks."""
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


TREE_DIGEST_EXCLUDES = (".git",)


def tree_digest(root: Path, excludes: Sequence[str] = ()) -> str:
    """A content hash of *root*, reproducible from the tree rather than from a zip."""
    hasher = hashlib.sha256()
    for entry in sorted(walk(root, (*excludes, *TREE_DIGEST_EXCLUDES)), key=lambda e: e.arcname):
        hasher.update(entry.arcname.encode("utf-8"))
        if entry.is_dir:
            hasher.update(b"\0dir")
        elif entry.is_symlink:
            hasher.update(b"\0link")
            hasher.update(os.readlink(entry.path).encode("utf-8"))
        else:
            hasher.update(b"\0file")
            hasher.update(entry.path.read_bytes())
        hasher.update(b"\0")
    return hasher.hexdigest()


def manifest(root: Path) -> dict[str, tuple[int, int, bool]]:
    """`{relative path: (size, mtime_ns, is_symlink)}` for every entry under *root*."""
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
