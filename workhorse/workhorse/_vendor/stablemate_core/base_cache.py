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

**The cache is never refreshed by a lookup, a resume, or a background timer.** It is
fetched when absent and then frozen, and that is load-bearing: workhorse's design target
is a run that survives a week unattended and resumes into a checkpointed state machine
after a crash, so a cache tracking ``main`` live could resume a run into a *different
library than it started with*. Fetch-once-then-freeze means the content a run starts with
is the content it finishes with.

What that argument does *not* cover is an operator standing at a terminal typing
``farrier install`` — a one-shot re-render of a repository, at a moment they chose. So
:func:`refresh_cached_base` exists for exactly that caller: it is the automated form of
the ``rm -rf ~/.cache/stablemate`` that used to be the only upgrade path, not a new
background behaviour. Nothing else calls it, and a run in flight elsewhere on the machine
is the one thing to keep in mind before doing so.

A refresh fails soft toward *keeping what works*: an unreachable remote, a refused fetch
or a broken clone each leave the existing cache untouched and return it, because a
``farrier install`` on a plane should render the library the machine already has rather
than none at all.

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
# Its own, much shorter budget: `ls-remote` transfers a few hundred bytes, and it runs on
# the latency path of every `farrier install`. Waiting five minutes on it would turn a
# flaky network into a hung command, when the right answer — "use the cache you have" — is
# available immediately.
_LS_REMOTE_TIMEOUT_S = 30


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


def _git(
    *args: str, cwd: Path | None = None, timeout: float = _CLONE_TIMEOUT_S
) -> subprocess.CompletedProcess | None:
    """Run git, or None if it could not run at all. Never raises."""
    cmd = ["git", *(["-C", str(cwd)] if cwd else []), *args]
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        )
    except subprocess.TimeoutExpired:
        logger.warning("timed out running `git %s` for the base library", args[0])
        return None
    except OSError as exc:
        # No git on PATH is the interesting case: report it as itself rather than as
        # "base library not found", which would send someone hunting the wrong bug.
        logger.warning("could not run git to fetch the base library: %s", exc)
        return None


def remote_commit() -> str | None:
    """The commit ``BASE_REPO_REF`` points at on the remote, or None if it cannot be read.

    A few hundred bytes over the wire, against the ~16M a clone moves. That asymmetry is
    the whole reason this exists: it lets :func:`refresh_cached_base` discover it has
    nothing to do without re-cloning to find out, so the common case of an already-current
    cache costs one round-trip rather than a full fetch-and-compare.

    None conflates "offline", "no git" and "the ref is gone" on purpose — every one of
    them means the same thing to the only caller: keep the cache you have.
    """
    proc = _git("ls-remote", BASE_REPO_URL, BASE_REPO_REF, timeout=_LS_REMOTE_TIMEOUT_S)
    if proc is None or proc.returncode != 0:
        return None
    # `<sha>\t<ref>` per line. A ref that matches nothing exits 0 with empty output,
    # which is why the emptiness is checked rather than the return code alone.
    first = proc.stdout.strip().split("\n", 1)[0].split()
    return first[0] if first else None


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


def refresh_cached_base(*, quiet: bool = False) -> Path | None:
    """Bring the cache up to date with ``BASE_REPO_REF``, then return it. None if unavailable.

    Fetches when absent (deferring to :func:`ensure_cached_base`), and otherwise replaces
    what is on disk when the remote has moved. Call this only from a command an operator
    invoked — see the module docstring for why every *other* caller must freeze instead.

    Every failure below returns the cache that is already there rather than None. That is
    the asymmetry worth keeping straight: a *fetch* that fails has nothing to hand back, so
    it degrades to "no library"; a *refresh* that fails still has a perfectly good library,
    and turning that into "no library" would make an offline machine strictly worse off for
    having asked.
    """
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
        # `_clone_into` already logged why.
        shutil.rmtree(tmp, ignore_errors=True)
        return existing
    if not is_library_dir(tmp / BASE_SUBPATH):
        # Refuse to swap in something that is not a library. Without this check a moved
        # layout upstream would replace a working cache with an unusable one, and the
        # damage would outlive the command that did it.
        logger.warning(
            "fetched %s but %s/ holds no library; keeping the cached copy",
            BASE_REPO_URL,
            BASE_SUBPATH,
        )
        shutil.rmtree(tmp, ignore_errors=True)
        return existing

    # Rename the old one aside, move the new one in, then delete. Two renames still leave
    # a window where a concurrent reader sees no cache, but it is two syscalls wide rather
    # than however long an rmtree of 16M takes — and, more to the point, a swap that dies
    # halfway has the old copy intact to put back, which delete-then-move does not.
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
