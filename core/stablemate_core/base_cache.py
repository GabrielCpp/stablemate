"""Fetch the base library into a shared cache, so every tool and venv sees one copy.

The base library is content — workflows, scaffolds, skills — with no code the tools
import beyond a path. That makes it fetchable the way any regenerable asset is: clone
it once into the user's cache and reuse it everywhere, instead of requiring a wheel in
each isolated pipx venv.

**The cache is never refreshed automatically.** It is cloned when absent and then left
alone; to move to a newer library, delete it and let the next run re-fetch. That is a
deliberate property, not an omission. Workhorse's design target is a run that survives
a week unattended, and it resumes into a checkpointed graph after a crash — if the
cache tracked ``main`` live, a run could resume into a *different workflow than it
started*, and the payload here is executed (``scripts/*.py`` run under
``sys.executable``), not inert data like a certifi ``.pem``. Fetch-once-then-freeze
means the content a run starts with is the content it finishes with.

The consequence, accepted knowingly: two machines can hold different commits of
``main``. ``cached_commit`` exists so that difference is at least visible.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from platformdirs import user_cache_dir

from stablemate_core.layout import is_library_dir

logger = logging.getLogger(__name__)

# Public, anonymous-cloneable. Not the `git@` remote a contributor pushes with: this
# runs on machines that have no deploy key and no business having one.
BASE_REPO_URL = "https://github.com/GabrielCpp/stablemate.git"
BASE_REPO_REF = "main"
# Where the library lives inside the repo. The payload sits directly here — `library/`,
# `scaffolds/`, `workflows/` — with no Python package wrapping it.
BASE_SUBPATH = "base-library"

# Opt-out: set to "0"/"false" to forbid the network fetch entirely (air-gapped hosts,
# or anyone who would rather a missing base be an error than a surprise download).
FETCH_ENV = "STABLEMATE_FETCH_BASE"
CACHE_DIR_ENV = "STABLEMATE_CACHE_DIR"

_CLONE_TIMEOUT_S = 300


def cache_root() -> Path:
    """The shared cache dir. XDG semantics: deletable at any time without loss.

    Which is exactly the contract we want — deleting it IS the upgrade path. Nothing
    here may be edited in place: it is a mirror, and the next delete takes edits with
    it. Overlay authoring belongs in a `library_dir`, not here.
    """
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
    """The commit the cache holds, or None. Makes "which library am I running" answerable.

    Worth recording in run artifacts: it is the only thing distinguishing two machines
    that both cloned `main` on different days.
    """
    root = clone or cached_library_dir()
    if not (root / ".git").is_dir():
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout.strip() or None


def _clone_into(dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    # A full clone is 11M against 2.5M for a sparse one -- an 8M saving that isn't
    # worth sparse-checkout's failure modes. Measured, not assumed.
    cmd = [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        BASE_REPO_REF,
        BASE_REPO_URL,
        str(dest),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=_CLONE_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired:
        logger.warning("timed out fetching the base library from %s", BASE_REPO_URL)
        return False
    except OSError as exc:
        # No git on PATH is the interesting case: report it as itself rather than as
        # "base library not found", which would send someone hunting the wrong bug.
        logger.warning("could not run git to fetch the base library: %s", exc)
        return False
    if proc.returncode != 0:
        logger.warning(
            "failed to fetch the base library from %s: %s",
            BASE_REPO_URL,
            proc.stderr.strip(),
        )
        return False
    return True


def cached_base() -> Path | None:
    """The cached base library if already on disk AND usable, else None. NEVER fetches.

    Split from :func:`ensure_cached_base` on purpose. Base-library resolution is a
    lookup, and a lookup that silently downloads 16M is a trap: `config show` would do
    it, and so would any test that resolves a path. Downloading is a side effect, so it
    gets its own function and an explicit caller.

    Validates the layout rather than just the path's existence. A cache fetched before
    the library was flattened has a ``base-library/`` *directory* holding a Python
    package — ``is_dir()`` alone would accept it, discovery would then reject it, and
    nothing would ever re-fetch. Checking the content turns that into a diagnosable
    state (see :func:`ensure_cached_base`) instead of a permanently dead cache.
    """
    base = cached_library_dir() / BASE_SUBPATH
    return base if is_library_dir(base) else None


def ensure_cached_base(*, quiet: bool = False) -> Path | None:
    """Return the cached base library, cloning it if absent. None if unavailable.

    Call this only where the library is actually *needed* (resolving a workflow name),
    never from a general lookup. Fail-soft by contract: every caller treats None as
    "not found here" and falls through, so an offline host behaves exactly as it did
    before this layer existed.
    """
    existing = cached_base()
    if existing is not None:
        return existing
    clone = cached_library_dir()
    base = clone / BASE_SUBPATH

    if clone.is_dir():
        # A cache exists but holds nothing usable — most likely fetched when the library
        # had a different layout. Re-fetching cannot fix it (the rename below would hit a
        # non-empty target), so say the one thing that will, rather than falling through
        # to a silent "no library found" that sends someone hunting their config.
        logger.warning(
            "the base library cache at %s holds no usable library (expected %s/ with "
            "library/ or workflows/ inside); delete it to re-fetch: rm -rf %s",
            clone,
            BASE_SUBPATH,
            cache_root(),
        )
        return None

    if not fetch_allowed():
        logger.debug("base fetch disabled via %s", FETCH_ENV)
        return None

    if not quiet:
        # Never fetch silently: this writes ~11M and touches the network, and an
        # operator watching an unattended run deserves to see why there's a pause.
        print(f"[stablemate] fetching base library: {BASE_REPO_URL} ({BASE_REPO_REF})")

    # Clone to a sibling temp dir, then rename into place. Two runs starting together
    # both fetch; the rename settles it without a lock file to leak if one is killed.
    tmp = clone.parent / f".library-fetch-{os.getpid()}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    if not _clone_into(tmp):
        shutil.rmtree(tmp, ignore_errors=True)
        return None

    try:
        tmp.rename(clone)
    except OSError:
        # Lost the race -- a concurrent run landed its clone first. Theirs is as good
        # as ours (same ref), so drop ours and use what's there.
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
