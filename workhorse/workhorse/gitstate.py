"""What the repo looked like — observed, never assumed."""

from __future__ import annotations

import json
import subprocess
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

TIMEOUT_S = 5.0

DEFAULT_TTL_S = 5.0


@dataclass(frozen=True, slots=True)
class RepoState:
    """One observation of one working tree, at one moment."""

    path: str = ""
    root: str = ""
    origin: str = ""
    head: str = ""
    branch: str = ""
    dirty: bool | None = None
    stash: str = ""

    @property
    def observed(self) -> bool:
        """Did this look at a working tree at all?"""
        return bool(self.head)

    def attributes(self, prefix: str) -> dict[str, str | bool]:
        """Telemetry attributes for this observation, omitting what was not observed."""
        attrs: dict[str, str | bool] = {}
        if self.head:
            attrs[f"{prefix}.head"] = self.head
        if self.origin:
            attrs[f"{prefix}.origin"] = self.origin
        if self.branch:
            attrs[f"{prefix}.branch"] = self.branch
        if self.dirty is not None:
            attrs[f"{prefix}.dirty"] = self.dirty
        if self.stash:
            attrs[f"{prefix}.stash"] = self.stash
        return attrs


def _git(path: str | Path, *args: str) -> str:
    """One git command in ``path``, or "" for every way it can fail to answer."""
    try:
        done = subprocess.run(
            ["git", "-C", str(path), *args],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if done.returncode != 0:
        return ""
    return done.stdout.strip()


def _identity(path: str | Path) -> tuple[str, str, str]:
    """Repository root, full HEAD, and branch in one git process; empties when absent."""
    lines = _git(path, "rev-parse", "--show-toplevel", "HEAD", "--abbrev-ref", "HEAD").splitlines()
    if len(lines) != 3:
        return "", "", ""
    root, head, branch = lines
    return root, head, "" if branch == "HEAD" else branch


def observe(path: str | Path, *, dirty: bool = True, stash: bool = False) -> RepoState:
    """Observe ``path``'s working tree."""
    root = _git(path, "rev-parse", "--show-toplevel")
    head = _git(path, "rev-parse", "HEAD")
    if not head:
        return RepoState(path=str(path))
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = ""
    is_dirty: bool | None = None
    if dirty:
        is_dirty = bool(_git(path, "status", "--porcelain"))
    blob = ""
    if stash and is_dirty is not False:
        blob = _git(path, "stash", "create")
    return RepoState(
        path=str(path),
        root=root,
        origin=_git(path, "remote", "get-url", "origin"),
        head=head,
        branch=branch,
        dirty=is_dirty,
        stash=blob,
    )


@dataclass(frozen=True, slots=True)
class DirectoryObservation:
    """One directory in an execution's declared filesystem scope."""

    path: str
    role: str
    vcs: str
    root: str = ""
    origin: str = ""
    branch: str = ""
    head: str = ""

    def as_dict(self) -> dict[str, str]:
        return {
            "path": self.path,
            "role": self.role,
            "vcs": self.vcs,
            "root": self.root,
            "origin": self.origin,
            "branch": self.branch,
            "head": self.head,
        }


@dataclass(frozen=True, slots=True)
class RepositorySnapshot:
    """Immutable git identities for a span's primary and additional directories."""

    directories: tuple[DirectoryObservation, ...] = ()

    def attributes(self) -> dict[str, str]:
        if not self.directories:
            return {}
        primary = self.directories[0]
        attrs = {
            "workspace.path": primary.path,
            "workspace.vcs": primary.vcs,
            "workhorse.repositories": json.dumps(
                [directory.as_dict() for directory in self.directories],
                separators=(",", ":"),
                sort_keys=True,
            ),
        }
        if primary.origin:
            attrs["git.origin"] = primary.origin
        if primary.branch:
            attrs["git.branch"] = primary.branch
        if primary.head:
            attrs["git.head"] = primary.head
        return attrs


def observe_scope(
    cwd: str | Path,
    add_dirs: Sequence[str | Path] = (),
) -> RepositorySnapshot:
    """Observe an execution's cwd and additional directories without dropping raw folders."""
    requested = ((cwd, "cwd"), *((path, "add_dir") for path in add_dirs))
    directories: list[DirectoryObservation] = []
    seen: set[tuple[str, str]] = set()
    for raw, role in requested:
        path = str(Path(raw).expanduser().resolve())
        root, head, branch = _identity(path)
        if not root:
            key = ("unversioned", path)
            if key not in seen:
                seen.add(key)
                directories.append(DirectoryObservation(path=path, role=role, vcs="unversioned"))
            continue
        root = str(Path(root).resolve())
        key = ("git", root)
        if key in seen:
            continue
        seen.add(key)
        directories.append(
            DirectoryObservation(
                path=path,
                role=role,
                vcs="git",
                root=root,
                origin=_git(root, "remote", "get-url", "origin"),
                branch=branch,
                head=head,
            )
        )
    return RepositorySnapshot(tuple(directories))


class HeadWatch:
    """A TTL-cached HEAD for one working tree."""

    __slots__ = ("_path", "_ttl_s", "_head", "_read_at", "_scopes")

    def __init__(self, path: str | Path, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._path = str(path)
        self._ttl_s = ttl_s
        self._head = ""
        self._read_at = 0.0
        self._scopes: dict[
            tuple[str, tuple[str, ...]], tuple[float, RepositorySnapshot]
        ] = {}

    @property
    def path(self) -> str:
        return self._path

    def head(self) -> str:
        """The current HEAD, re-reading only once the cached one is past its TTL."""
        now = time.monotonic()
        if self._head and now - self._read_at < self._ttl_s:
            return self._head
        return self.refresh()

    def refresh(self) -> str:
        """Re-read HEAD now, whatever the cache says."""
        self._head = _git(self._path, "rev-parse", "HEAD")
        self._read_at = time.monotonic()
        return self._head

    def state(self, *, dirty: bool = True, stash: bool = False) -> RepoState:
        """A full observation, which also refreshes the cached HEAD — a boundary that wants the whole picture has by definition just paid for the hash."""
        observed = observe(self._path, dirty=dirty, stash=stash)
        self._head = observed.head
        self._read_at = time.monotonic()
        return observed

    def scope(
        self,
        cwd: str | Path | None = None,
        add_dirs: Sequence[str | Path] = (),
        *,
        refresh: bool = False,
    ) -> RepositorySnapshot:
        """Observe one directory scope, reusing its last boundary snapshot briefly."""
        primary = str(cwd if cwd is not None else self._path)
        additional = tuple(str(path) for path in add_dirs)
        key = (primary, additional)
        now = time.monotonic()
        cached = self._scopes.get(key)
        if not refresh and cached is not None and now - cached[0] < self._ttl_s:
            return cached[1]
        snapshot = observe_scope(primary, additional)
        self._scopes[key] = (now, snapshot)
        return snapshot


_watch: HeadWatch | None = None


def bind(path: str | Path, ttl_s: float = DEFAULT_TTL_S) -> None:
    """Point the module-level observer at this run's working tree."""
    global _watch
    _watch = HeadWatch(path, ttl_s)


def unbind() -> None:
    """Forget the bound tree."""
    global _watch
    _watch = None


def bound() -> HeadWatch | None:
    """The bound observer, or None when nothing bound one — a library caller, a test, or a run whose start failed before this point."""
    return _watch


def current_head(*, refresh: bool = False) -> str:
    """The bound tree's HEAD; "" when nothing is bound or it is not a repo."""
    watch = _watch
    if watch is None:
        return ""
    return watch.refresh() if refresh else watch.head()


def current_state(*, dirty: bool = True, stash: bool = False) -> RepoState:
    """A full observation of the bound tree; an empty state when nothing is bound."""
    watch = _watch
    return watch.state(dirty=dirty, stash=stash) if watch is not None else RepoState()


def current_scope(
    cwd: str | Path | None = None,
    add_dirs: Sequence[str | Path] = (),
    *,
    refresh: bool = False,
) -> RepositorySnapshot:
    """Observe an explicit execution scope, defaulting its cwd to the bound workspace."""
    watch = _watch
    if watch is None:
        return RepositorySnapshot()
    return watch.scope(cwd, add_dirs, refresh=refresh)
