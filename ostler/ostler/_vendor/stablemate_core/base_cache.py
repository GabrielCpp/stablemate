"""Fetch the base library into a shared cache, so every tool and venv sees one copy."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from platformdirs import user_cache_dir

from .layout import is_library_dir

logger = logging.getLogger(__name__)

BASE_REPO_URL = "https://github.com/GabrielCpp/stablemate.git"
BASE_REPO_REF = "main"
BASE_SUBPATH = "base-library"

COMMIT_FILE = ".commit"

FETCH_ENV = "STABLEMATE_FETCH_BASE"
CACHE_DIR_ENV = "STABLEMATE_CACHE_DIR"

_CLONE_TIMEOUT_S = 300
_LS_REMOTE_TIMEOUT_S = 30


def cache_root() -> Path:
    """The shared cache dir."""
    override = os.environ.get(CACHE_DIR_ENV)
    if override:
        return Path(override).expanduser()
    return Path(user_cache_dir("stablemate"))


def cached_library_dir() -> Path:
    return cache_root() / "library"


def fetch_allowed() -> bool:
    raw = os.environ.get(FETCH_ENV)
    if raw is None:
        return True
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def cached_commit(clone: Path | None = None) -> str | None:
    """The commit the cache holds, or None."""
    root = clone or cached_library_dir()
    try:
        return (root / COMMIT_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _git(
    *args: str, cwd: Path | None = None, timeout: float = _CLONE_TIMEOUT_S
) -> subprocess.CompletedProcess | None:
    """Run git, or None if it could not run at all."""
    cmd = ["git", *(["-C", str(cwd)] if cwd else []), *args]
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        logger.warning("timed out running `git %s` for the base library", args[0])
        return None
    except OSError as exc:
        logger.warning("could not run git to fetch the base library: %s", exc)
        return None


def remote_commit() -> str | None:
    """The commit ``BASE_REPO_REF`` points at on the remote, or None if it cannot be read."""
    proc = _git("ls-remote", BASE_REPO_URL, BASE_REPO_REF, timeout=_LS_REMOTE_TIMEOUT_S)
    if proc is None or proc.returncode != 0:
        return None
    first = proc.stdout.strip().split("\n", 1)[0].split()
    return first[0] if first else None


def _clone_into(dest: Path) -> bool:
    """Sparse-fetch ``base-library/`` into ``dest``, then leave documents behind."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    steps: list[tuple[str, list[str], Path | None]] = [
        (
            "clone",
            [
                "clone",
                "--depth=1",
                f"--branch={BASE_REPO_REF}",
                "--filter=blob:none",
                "--sparse",
                BASE_REPO_URL,
                str(dest),
            ],
            None,
        ),
        (
            "sparse-checkout",
            ["sparse-checkout", "set", "--no-cone", f"/{BASE_SUBPATH}/"],
            dest,
        ),
        ("checkout", ["checkout", BASE_REPO_REF], dest),
    ]
    for label, args, cwd in steps:
        proc = _git(*args, cwd=cwd)
        if proc is None:
            return False
        if proc.returncode != 0:
            logger.warning(
                "failed to fetch the base library from %s (git %s): %s",
                BASE_REPO_URL,
                label,
                proc.stderr.strip(),
            )
            return False

    head = _git("rev-parse", "HEAD", cwd=dest)
    commit = head.stdout.strip() if head and head.returncode == 0 else ""
    (dest / COMMIT_FILE).write_text(f"{commit}\n", encoding="utf-8")
    shutil.rmtree(dest / ".git", ignore_errors=True)
    return True


def cached_base() -> Path | None:
    """The cached base library if already on disk AND usable, else None."""
    base = cached_library_dir() / BASE_SUBPATH
    return base if is_library_dir(base) else None


def ensure_cached_base(*, quiet: bool = False) -> Path | None:
    """Return the cached base library, fetching it if absent."""
    existing = cached_base()
    if existing is not None:
        return existing
    clone = cached_library_dir()
    base = clone / BASE_SUBPATH

    if clone.is_dir():
        logger.warning(
            "the base library cache at %s holds no usable library (expected %s/ with "
            "library/ inside); delete it to re-fetch: rm -rf %s",
            clone,
            BASE_SUBPATH,
            cache_root(),
        )
        return None

    if not fetch_allowed():
        logger.debug("base fetch disabled via %s", FETCH_ENV)
        return None

    if not quiet:
        print(
            f"[stablemate] fetching base library: {BASE_REPO_URL} "
            f"({BASE_REPO_REF}, {BASE_SUBPATH}/ only)"
        )

    tmp = clone.parent / f".library-fetch-{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    if not _clone_into(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    try:
        tmp.rename(clone)
    except OSError:
        shutil.rmtree(tmp, ignore_errors=True)

    if not base.is_dir():
        logger.warning(
            "fetched %s but %s is missing; the library layout may have moved",
            BASE_REPO_URL,
            BASE_SUBPATH,
        )
        return None
    if not quiet:
        print(f"[stablemate] base library cached at {clone} ({cached_commit() or '?'})")
    return base


def refresh_cached_base(*, quiet: bool = False) -> Path | None:
    """Bring the cache up to date with ``BASE_REPO_REF``, then return it."""
    existing = cached_base()
    if existing is None:
        return ensure_cached_base(quiet=quiet)
    if not fetch_allowed():
        logger.debug("base refresh disabled via %s", FETCH_ENV)
        return existing

    local = cached_commit()
    remote = remote_commit()
    if remote is None:
        if not quiet:
            print(
                "[stablemate] could not reach the base library remote; "
                f"using the cached copy ({local or '?'})"
            )
        return existing
    if remote == local:
        return existing

    if not quiet:
        print(
            f"[stablemate] updating base library: {(local or '?')[:12]} -> {remote[:12]} "
            f"({BASE_REPO_URL}, {BASE_REPO_REF})"
        )

    clone = cached_library_dir()
    tmp = clone.parent / f".library-fetch-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    if not _clone_into(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        return existing
    if not is_library_dir(tmp / BASE_SUBPATH):
        logger.warning(
            "fetched %s but %s/ holds no library; keeping the cached copy",
            BASE_REPO_URL,
            BASE_SUBPATH,
        )
        shutil.rmtree(tmp, ignore_errors=True)
        return existing

    superseded = clone.parent / f".library-old-{os.getpid()}"
    shutil.rmtree(superseded, ignore_errors=True)
    try:
        clone.rename(superseded)
        tmp.rename(clone)
    except OSError as exc:
        logger.warning("could not swap the refreshed base library into place: %s", exc)
        shutil.rmtree(tmp, ignore_errors=True)
        if superseded.is_dir() and not clone.exists():
            superseded.rename(clone)
        return cached_base() or existing
    shutil.rmtree(superseded, ignore_errors=True)

    refreshed = cached_base()
    if refreshed is None:
        logger.warning("the refreshed base library at %s is not usable", clone)
        return existing
    if not quiet:
        print(f"[stablemate] base library updated at {clone} ({cached_commit() or '?'})")
    return refreshed
