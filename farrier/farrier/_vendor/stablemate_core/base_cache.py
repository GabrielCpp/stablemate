"""Fetch the base library into a shared cache, so every tool and venv sees one copy.

The base library is content — skills, prompts, scaffolds — with no code the tools
import beyond a path. That makes it fetchable the way any regenerable asset is: fetch
it once into the user's cache and reuse it everywhere, instead of requiring a wheel in
each isolated pipx venv.

**The cache holds documents, not a repository.** The fetch is a sparse checkout of
``base-library/`` alone, and the ``.git`` directory is removed once the commit is
recorded. This is the trust posture, and it is the whole answer to "is it safe to
download this": *nothing fetched is executable*. ``base-library/`` is markdown and YAML
end to end. Code arrives only as a wheel from an index, under whatever supply-chain
posture the operator already applies to ``pip``/``uv`` — a boring existing answer rather
than a new one invented for a git cache. It was not always so: the base shipped four
directories of workflow YAML with 127 ``scripts/*.py`` that ran under ``sys.executable``,
and while that was true a narrow fetch would have been a false reassurance. Retiring the
YAML front-end is what earned this.

Fail closed. If the sparse checkout cannot be set up, the fetch fails rather than falling
back to a full clone — a silent fallback would hand back the property above without
saying so.

**The cache is never refreshed automatically.** It is fetched when absent and then left
alone; to move to a newer library, delete it and let the next run re-fetch. That is a
deliberate property, not an omission. Workhorse's design target is a run that survives
a week unattended, and it resumes into a checkpointed state machine after a crash — if
the cache tracked ``main`` live, a run could resume into a *different library than it
started with*. Fetch-once-then-freeze means the content a run starts with is the content
it finishes with.

The consequence, accepted knowingly: two machines can hold different commits of
``main``. ``cached_commit`` exists so that difference is at least visible — it reads the
sidecar the fetch writes, since there is no ``.git`` left to ask.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path

from platformdirs import user_cache_dir

from .layout import is_library_dir

logger = logging.getLogger(__name__)

# Public, anonymous-cloneable. Not the `git@` remote a contributor pushes with: this
# runs on machines that have no deploy key and no business having one.
BASE_REPO_URL = "https://github.com/GabrielCpp/stablemate.git"
BASE_REPO_REF = "main"
# Where the library lives inside the repo. The payload sits directly here — `library/`
# and `scaffolds/` — with no Python package wrapping it.
BASE_SUBPATH = "base-library"

# Where the fetch records the commit it took, since `.git` does not survive it. A plain
# file so nothing has to shell out to read it, and so a cache assembled by hand (an
# air-gapped host copying the directory in) can say what it holds.
COMMIT_FILE = ".commit"

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
    that both fetched `main` on different days. Read from the ``.commit`` sidecar the
    fetch writes — the cache is documents, so there is no `.git` to `rev-parse`.
    """
    root = clone or cached_library_dir()
    try:
        return (root / COMMIT_FILE).read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def _git(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess | None:
    """Run git, or None if it could not run at all. Never raises."""
    cmd = ["git", *(["-C", str(cwd)] if cwd else []), *args]
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=_CLONE_TIMEOUT_S, check=False
        )
    except subprocess.TimeoutExpired:
        logger.warning("timed out running `git %s` for the base library", args[0])
        return None
    except OSError as exc:
        # No git on PATH is the interesting case: report it as itself rather than as
        # "base library not found", which would send someone hunting the wrong bug.
        logger.warning("could not run git to fetch the base library: %s", exc)
        return None


def _clone_into(dest: Path) -> bool:
    """Sparse-fetch ``base-library/`` into ``dest``, then leave documents behind.

    Four steps, all of which must succeed: clone with no working tree and no blobs, set
    the sparse cone to `base-library/`, check it out, record HEAD and drop `.git`. There
    is deliberately no fallback to a full clone — see the module docstring. A git too old
    for `sparse-checkout` (< 2.25) fails here with git's own message.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    steps: list[tuple[str, list[str], Path | None]] = [
        # `--filter=blob:none` is what makes the narrowing a *transfer* saving and not
        # just a checkout one: without it git sends every blob of the commit and sparse
        # checkout merely declines to write them.
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
        # `--no-cone` rather than the default cone mode, because cone mode always
        # checks out the repository root as well — `pyproject.toml`, `Makefile`,
        # `uv.lock`, the whole top level. Inert, but not documents, and "only the
        # library" should mean it. If a future git drops `--no-cone` this exits
        # non-zero and the fetch fails, which is the right way to find out.
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
    # Record before dropping `.git`: afterwards there is nothing left to ask, and an
    # unidentifiable cache is the one thing `cached_commit` exists to prevent.
    (dest / COMMIT_FILE).write_text(f"{commit}\n", encoding="utf-8")
    shutil.rmtree(dest / ".git", ignore_errors=True)
    return True


def cached_base() -> Path | None:
    """The cached base library if already on disk AND usable, else None. NEVER fetches.

    Split from :func:`ensure_cached_base` on purpose. Base-library resolution is a
    lookup, and a lookup that silently reaches the network is a trap: `config show` would
    do it, and so would any test that resolves a path. Downloading is a side effect, so
    it gets its own function and an explicit caller.

    Validates the layout rather than just the path's existence. A cache fetched before
    the library was flattened has a ``base-library/`` *directory* holding a Python
    package — ``is_dir()`` alone would accept it, discovery would then reject it, and
    nothing would ever re-fetch. Checking the content turns that into a diagnosable
    state (see :func:`ensure_cached_base`) instead of a permanently dead cache.
    """
    base = cached_library_dir() / BASE_SUBPATH
    return base if is_library_dir(base) else None


def ensure_cached_base(*, quiet: bool = False) -> Path | None:
    """Return the cached base library, fetching it if absent. None if unavailable.

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
        # Never fetch silently: this touches the network and writes to the cache, and an
        # operator watching an unattended run deserves to see why there's a pause.
        print(
            f"[stablemate] fetching base library: {BASE_REPO_URL} "
            f"({BASE_REPO_REF}, {BASE_SUBPATH}/ only)"
        )

    # Fetch to a sibling temp dir, then rename into place. Two runs starting together
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
