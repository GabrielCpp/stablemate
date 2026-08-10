"""What the repo looked like — observed, never assumed.

A run's telemetry says a node was entered and a turn was spent; it does not say what
tree the agent was reading while it spent it. Without that, a recorded turn cannot be
matched to the code it saw, and the transcript archive built on top of it degrades from
"what happened, against what" into "what happened, somewhere".

The engine must not model *why* the tree moves. A workflow node may commit, a story
node may branch, the agent inside a turn may check out a tag or rebase, and none of
that is workhorse's to predict — workhorse drives arbitrary workflows over arbitrary
repos, and the cwd may not even be a working tree. So this module **observes**: it
reports `head`/`branch`/`dirty` at the moments the engine already has, records them as
facts, and asserts nothing about two observations being equal. A span whose
``git.head.start`` and ``git.head.end`` differ is not an error — it is the record that
something moved HEAD inside that span, which is exactly the thing a reader would
otherwise have no way to discover.

Two rules the callers depend on:

**Nothing here may fail a run.** Every git invocation is best-effort behind a short
timeout, and every failure — no git on PATH, not a repo, a corrupt index, a hung
filesystem — yields an empty field rather than an exception. This is diagnostic
metadata; a run that dies because it could not describe itself has traded the thing for
the description of the thing.

**HEAD is cached.** :class:`HeadWatch` holds the last observation and re-reads it only
past a TTL or when a boundary explicitly refreshes it. That is what makes stamping
*every log record* affordable: a `git rev-parse` per line would put a subprocess on the
path of every `logger.info` in the engine. The cost of the cache is that a log emitted
seconds after a mid-turn checkout may carry the previous hash — acceptable, because the
span endpoints bracket the move regardless, and the alternative is not stamping logs at
all.

``stash`` is separate from the rest and never automatic. ``git stash create`` writes a
commit object for the working tree without touching the index, the worktree or the
stash ref — cheap and side-effect-free as far as the run is concerned, but it does add
loose objects, so it is taken only where a caller has decided the WIP is worth
recording.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

#: Seconds any single git invocation gets. Generous for `rev-parse` on a warm repo and
#: still short enough that a wedged filesystem costs the run a pause, not a hang.
TIMEOUT_S = 5.0

#: How long a cached HEAD is trusted without re-reading. Sized against what reads it:
#: log records, which arrive in bursts within one node's work, where the answer does
#: not change. Boundaries refresh explicitly rather than waiting this out.
DEFAULT_TTL_S = 5.0


@dataclass(frozen=True, slots=True)
class RepoState:
    """One observation of one working tree, at one moment.

    Every field defaults to empty/None, and empty means *not observed* — never
    "clean", never "no commits". A caller rendering this into telemetry drops the empty
    ones rather than exporting a false zero: an attribute that is absent is honest
    about a repo-less cwd, whereas ``dirty=false`` on a directory that is not a repo is
    a claim nobody made.
    """

    #: The directory observed. Kept on the record because a run may span several
    #: repos, so an observation is only meaningful next to what it observed.
    path: str = ""
    head: str = ""
    branch: str = ""
    #: Tri-state on purpose: True/False are observations, None is "did not look" or
    #: "could not tell".
    dirty: bool | None = None
    #: A `git stash create` commit for the uncommitted work, when one was requested and
    #: there was any. Empty otherwise — including on a clean tree, which has no WIP to
    #: snapshot rather than an empty one.
    stash: str = ""

    @property
    def observed(self) -> bool:
        """Did this look at a working tree at all?"""
        return bool(self.head)

    def attributes(self, prefix: str) -> dict[str, str | bool]:
        """Telemetry attributes for this observation, omitting what was not observed.

        ``prefix`` is the full key stem — ``"git.head.start"`` style keys come from
        callers passing ``"git"`` plus their own suffix, so this stays ignorant of
        whether it is describing a start, an end, or a standalone sample.
        """
        attrs: dict[str, str | bool] = {}
        if self.head:
            attrs[f"{prefix}.head"] = self.head
        if self.branch:
            attrs[f"{prefix}.branch"] = self.branch
        if self.dirty is not None:
            attrs[f"{prefix}.dirty"] = self.dirty
        if self.stash:
            attrs[f"{prefix}.stash"] = self.stash
        return attrs


def _git(path: str | Path, *args: str) -> str:
    """One git command in ``path``, or "" for every way it can fail to answer.

    Deliberately swallowing: see the module docstring. The callers are all recording
    metadata about a run that is doing something else, and none of them has a
    meaningful recovery for "git did not answer" beyond leaving the field empty.
    """
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


def observe(path: str | Path, *, dirty: bool = True, stash: bool = False) -> RepoState:
    """Observe ``path``'s working tree. Returns an empty state for a non-repo.

    ``dirty`` is opt-out because `git status --porcelain` walks the tree and a large
    repo makes it the expensive call here, while `rev-parse` is effectively free. A
    caller sampling frequently turns it off; a caller marking a boundary leaves it on.
    """
    head = _git(path, "rev-parse", "HEAD")
    if not head:
        # No HEAD is the one answer that means "there is nothing here to describe" —
        # not a repo, no git, or a repo with no commits yet. Everything below would be
        # empty anyway, and skipping it keeps the non-repo case to a single subprocess.
        return RepoState(path=str(path))
    # `--show-current` is empty on a detached HEAD, which is a true answer: there is no
    # branch. It is not turned into the hash, because "branch = <sha>" would read as a
    # branch named after a commit.
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    if branch == "HEAD":
        branch = ""
    is_dirty: bool | None = None
    if dirty:
        is_dirty = bool(_git(path, "status", "--porcelain"))
    blob = ""
    if stash and is_dirty is not False:
        # Empty output on a clean tree — `stash create` declines to make a commit with
        # nothing in it, which is why this is not conditioned on `is_dirty` being True:
        # a caller that skipped the status walk still gets the right answer.
        blob = _git(path, "stash", "create")
    return RepoState(path=str(path), head=head, branch=branch, dirty=is_dirty, stash=blob)


class HeadWatch:
    """A TTL-cached HEAD for one working tree.

    Not thread-safe by lock, and deliberately so: the worst a race does here is two
    threads both re-reading HEAD and both storing the same answer. A lock on the path
    that every log record takes would cost more than the duplicate it prevents.
    """

    __slots__ = ("_path", "_ttl_s", "_head", "_read_at")

    def __init__(self, path: str | Path, ttl_s: float = DEFAULT_TTL_S) -> None:
        self._path = str(path)
        self._ttl_s = ttl_s
        self._head = ""
        self._read_at = 0.0

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
        """Re-read HEAD now, whatever the cache says. Called at boundaries, where the
        engine already knows something may have moved."""
        self._head = _git(self._path, "rev-parse", "HEAD")
        self._read_at = time.monotonic()
        return self._head

    def state(self, *, dirty: bool = True, stash: bool = False) -> RepoState:
        """A full observation, which also refreshes the cached HEAD — a boundary that
        wants the whole picture has by definition just paid for the hash."""
        observed = observe(self._path, dirty=dirty, stash=stash)
        self._head = observed.head
        self._read_at = time.monotonic()
        return observed


#: The run's working tree, bound once at run start. Module-level for the same reason
#: `otel.current_node()` is: the log filter that stamps records has no argument to
#: carry it through, and the alternative — threading a repo path into every logging
#: call site in the engine — is a change to code that has nothing to do with git.
_watch: HeadWatch | None = None


def bind(path: str | Path, ttl_s: float = DEFAULT_TTL_S) -> None:
    """Point the module-level observer at this run's working tree."""
    global _watch
    _watch = HeadWatch(path, ttl_s)


def unbind() -> None:
    """Forget the bound tree. Tests use this; a run does not need to."""
    global _watch
    _watch = None


def bound() -> HeadWatch | None:
    """The bound observer, or None when nothing bound one — a library caller, a test,
    or a run whose start failed before this point."""
    return _watch


def current_head(*, refresh: bool = False) -> str:
    """The bound tree's HEAD; "" when nothing is bound or it is not a repo.

    This is what stamps a log record, so it must be cheap and must never raise —
    hence cached by default. ``refresh`` is for the boundaries that exist precisely to
    catch a move: a span's close, a turn's open.
    """
    watch = _watch
    if watch is None:
        return ""
    return watch.refresh() if refresh else watch.head()


def current_state(*, dirty: bool = True, stash: bool = False) -> RepoState:
    """A full observation of the bound tree; an empty state when nothing is bound."""
    watch = _watch
    return watch.state(dirty=dirty, stash=stash) if watch is not None else RepoState()
