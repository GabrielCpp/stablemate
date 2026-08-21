"""Pin the project a run drives, so a round measures one state of the code.

A task drives stablemate's own CLIs out of a checkout — `uv run --project <checkout>
workhorse-coder run …`. Left as the operator's working tree, that checkout is being
edited while the round runs: a forty-minute trial can start on one workflow source and
finish on another, and nothing in the result says which one it measured. It also makes
the "did the round commit into the harness instead of its sandbox" check unanswerable,
because an operator commit and a leaked agent commit land in the same tree and look
identical.

So paddock gives the run a repository of its own: a local clone of the checkout, with
**every remote removed**, checked out detached at the checkout's HEAD, created before the
first step and deleted after sealing. Three things follow, and they are the whole reason:

* the pinned sha goes into `steps.json`, so the ledger says which code produced the
  numbers;
* uncommitted edits are **excluded** — a round measures committed state, and a dirty
  checkout is warned about rather than silently included;
* the trial tree is not a git repository while the round runs — its git directory is
  stashed beside it — so a round cannot commit into the toolchain the ordinary way, and
  `escaped` says at seal whether it edited the tree anyway, built itself a repository to
  commit into, or found the stash and committed through that.

A clone rather than a `git worktree`, and remoteless rather than merely detached, because
a worktree of the live checkout shares its object store *and* its `origin`. One round
proved what that costs: an agent working inside the pinned tree read the toolchain repo's
own AGENTS.md — "push it now, right after the commit" — obeyed it to the letter, hit a
rejection, and followed the reconcile procedure written directly beneath it. Its commits
reached the public repo. The agent was not rogue; it was obedient in the wrong context,
and no instruction file can be trusted to say "unless you are a benchmark subject". Zero
remotes is what makes a push fail loudly instead of succeeding, and the failure lands in
the run record where a reader will find it.

The git directory is stashed rather than deleted because the round still has to be
*asked* about afterwards. What the pin gets in its place is a gitfile naming a path that
does not exist, which does two things a plain deletion would not: every git command inside
the pin fails with the reason printed in the error, and — the part that matters — git stops
walking up. Without it, `git commit` in a work directory that happens to sit under some
other repository would quietly land there instead, which is the same defect one directory
further out.

None of this is a proof, and the stash is the clearest reason why: it sits one directory
up from the round's own sandbox, so `ls ..` finds a whole repository, and `git init` gets
past the fence for anyone who does not. Both are reported rather than prevented. The
barrier is aimed at the shape the incident actually had — an obedient agent following an
instruction file written for a different context — and the detector is aimed at everything
past it, on the principle that a round which cannot be caught is worse than one which is
merely caught late. Nothing at this layer stops a round from walking to the operator's
checkout by absolute path either — that is a sandbox's job, not a benchmark harness's.

The cost is one `uv sync` per run into the clone's own `.venv` (wheels come from uv's
cache, so it is seconds, not a build) and the disk that venv takes until release. The
clone itself is local, so git hardlinks the objects and it is neither.

What this does *not* pin is the data directory: the answer key, the fixture app and the
result pointers are read and written in the operator's tracked tree on purpose — a score
whose ruler travelled inside the thing being measured would be worse than an unpinned one.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Project:
    """The tree a run's steps drive, and where it came from."""

    #: What a step should pass to `uv run --project` and stand in.
    path: Path
    #: The checkout `path` was pinned from — `path` itself when nothing was pinned.
    source: Path
    #: The commit the round ran at; empty when the source is not a git repository.
    head: str
    #: False when the run drives the operator's tree directly (`--no-pin-project`, or a
    #: source git cannot make a worktree of).
    pinned: bool
    #: Whether the source had uncommitted changes at pin time. Recorded because those
    #: changes are exactly what a pinned run did *not* see.
    dirty: bool
    #: Where the pin's own git directory was stashed while the round ran, or None when
    #: nothing was pinned. Reads about the pinned tree — is it dirty, what is it at — go
    #: through this, because the tree itself is deliberately not a repository.
    git_dir: Path | None = None
    #: Every `refs/remotes/…` ref in the source and where it pointed at pin time, as
    #: `(ref, sha)` pairs. Kept so `escaped` can ask the only question worth asking at
    #: seal — not "did the remote move", which it does all day because other people are
    #: working, but "did it move while this round was making commits of its own".
    remote_refs: tuple[tuple[str, str], ...] = ()
    #: Every ref in the *pin itself* and where it pointed at pin time. The fence stops a
    #: round from committing in the pinned tree the obvious way; this is what notices when
    #: it found the stashed git directory and committed through that instead.
    pin_refs: tuple[tuple[str, str], ...] = ()

    def as_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "source": str(self.source),
            "head": self.head,
            "pinned": self.pinned,
            "source_dirty": self.dirty,
        }


#: What a caveat says when the round, rather than an operator, is what compromised it.
#: A fixed prefix because it also travels into the result pointer, where the reader is a
#: script; the sentence after it is for the human.
SELF_TOUCHED = "self-touched: "

#: The nonexistent gitdir the pin's `.git` points at while the round runs. A sentence
#: rather than a name, because git prints it verbatim in the error an agent will read.
FENCE = "the-toolchain-is-off-limits-to-this-round"

#: What the pin's `.git` contains once fenced. Compared byte for byte at seal: a round
#: that wanted a repository badly enough to make one leaves this file changed or gone.
FENCE_GITFILE = f"gitdir: ./{FENCE}\n"


def stashed_git_dir(pinned_path: Path) -> Path:
    """Where `fence` put the pin's git directory — the convention, in one place.

    Beside the pin rather than inside it, so that deleting the pin does not take the only
    record of what it was with it, and so that a round working inside the pin does not
    find it by looking down. It does find it by looking *up*, and that is not fixable by
    moving it — `_describe` and `escaped` both have to read through it, so it is
    discoverable by construction. What answers the route is `escaped`, which asks this
    directory at seal what the round did to it.
    """
    return pinned_path.parent / "project.git"


def _git(
    *args: str, cwd: Path, git_dir: Path | None = None
) -> subprocess.CompletedProcess[str]:
    where = ["--git-dir", str(git_dir), "--work-tree", str(cwd)] if git_dir else []
    return subprocess.run(
        ["git", *where, *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )


def read(project: Project, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command against the pinned tree, fenced or not.

    Callers outside this module — the task-level leak check, mainly — need this rather
    than a bare `git -C <pin>`: once fenced, the pin is not a repository and a bare call
    fails with the fence's own error message, which is the correct answer to a *write*
    and the wrong one to a question.
    """
    return _git(*args, cwd=project.path, git_dir=project.git_dir)


def pin(source: Path | None, *, work: Path, enabled: bool = True) -> Project | None:
    """A remoteless clone of *source*, detached at its HEAD, under *work*.

    Degrades rather than fails: a source that is not a git repository, or a clone that
    will not run, leaves the run driving the operator's tree with `pinned: False` in the
    ledger. A benchmark that refuses to start because the harness could not make a clone
    helps nobody; a benchmark that silently claims a provenance it does not have is the
    failure worth avoiding, and the flag in the ledger is what avoids it.

    The one thing it will not degrade past is the remote. A clone that kept `origin`
    would be a pin in name only, so a failure to strip it discards the tree and runs
    unpinned rather than handing a round a route to the network.
    """
    if source is None:
        return None
    source = source.resolve()
    head = _git("rev-parse", "HEAD", cwd=source)
    if head.returncode != 0:
        logger.warning("project %s is not a git checkout — running unpinned", source)
        return Project(path=source, source=source, head="", pinned=False, dirty=False)
    sha = head.stdout.strip()
    dirty = bool(_git("status", "--porcelain", cwd=source).stdout.strip())
    refs = _remote_refs(source)
    if not enabled:
        return Project(
            path=source, source=source, head=sha, pinned=False, dirty=dirty, remote_refs=refs
        )

    dest = work / "project"
    # Re-running a label reuses its work directory, and a clone will not write into a
    # path that already exists.
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    unpinned = Project(
        path=source, source=source, head=sha, pinned=False, dirty=dirty, remote_refs=refs
    )
    # `--no-checkout`, because the branch a clone would land on is not the state being
    # pinned: the detached checkout below is, and doing it in one step would write the
    # tree twice.
    cloned = _git("clone", "--quiet", "--no-checkout", str(source), str(dest), cwd=work.parent)
    if cloned.returncode != 0:
        logger.warning(
            "could not clone %s (%s) — running unpinned", source, cloned.stderr.strip()
        )
        return unpinned
    for remote in _git("remote", cwd=dest).stdout.split():
        if _git("remote", "remove", remote, cwd=dest).returncode != 0:
            logger.warning(
                "could not strip remote %r from the pin of %s — running unpinned, and "
                "deleting the clone rather than leaving a round a route to the network",
                remote, source,
            )
            shutil.rmtree(dest, ignore_errors=True)
            return unpinned
    checked_out = _git("checkout", "--detach", sha, cwd=dest)
    if checked_out.returncode != 0:
        logger.warning(
            "could not check %s out at %s (%s) — running unpinned",
            source, sha[:12], checked_out.stderr.strip(),
        )
        shutil.rmtree(dest, ignore_errors=True)
        return unpinned
    # Asked while the clone is still a repository, because after the next three lines it
    # is not one — and this is the state `escaped` compares against at seal.
    pin_refs = _pairs(_git(*_REF_FORMAT, cwd=dest))
    stash = stashed_git_dir(dest)
    shutil.rmtree(stash, ignore_errors=True)
    (dest / ".git").rename(stash)
    (dest / ".git").write_text(FENCE_GITFILE, encoding="utf-8")
    if dirty:
        logger.warning(
            "%s has uncommitted changes; this run is pinned to %s and will not see them",
            source, sha[:12],
        )
    logger.info("project pinned to %s at %s", dest, sha[:12])
    return Project(
        path=dest, source=source, head=sha, pinned=True, dirty=dirty,
        git_dir=stash, remote_refs=refs, pin_refs=pin_refs,
    )


#: Every ref, not a prefix: a round that made a branch, a tag or a note in the pin all
#: answer the same question, and naming prefixes here is how one of them gets forgotten.
_REF_FORMAT = ("for-each-ref", "--format=%(refname) %(objectname)")


def _pairs(listed: subprocess.CompletedProcess[str]) -> tuple[tuple[str, str], ...]:
    split = (line.split(" ", 1) for line in listed.stdout.splitlines() if " " in line)
    return tuple(sorted((ref, sha) for ref, sha in split))


def _remote_refs(repo: Path) -> tuple[tuple[str, str], ...]:
    return _pairs(_git(*_REF_FORMAT, "refs/remotes", cwd=repo))


def escaped(project: Project | None) -> tuple[str, ...]:
    """Whether the round reached past its pin — asked while the pin still exists.

    The pin is fenced and has no remotes, so in the ordinary case this is silent and costs
    a handful of `git` calls. It exists because the fence is a barrier, not a proof: a
    round that edited the toolchain, or built itself a repository to commit into, did
    something a benchmark subject has no reason to do, and saying so in one line beats
    reconstructing it later from four sessions' reflogs.

    Three of its arms ask the *stashed* git directory rather than the pinned tree, and
    they ask unconditionally. The fence takes away the obvious way to commit into the
    toolchain; it does not take away the stash, which sits one directory up from the
    round's own sandbox and is a whole repository to anyone who runs `ls ..`. A round that
    committed through it leaves the fence intact and, if it committed rather than merely
    edited, leaves the tree clean — so every check keyed on the fence or on `status` reads
    that round as untouched. What it cannot leave alone is the repository: HEAD moves off
    the pinned sha, or a ref appears, or — for the round that patched, ran the patch, and
    reset back to look innocent — an object exists that the pinned sha does not reach.

    The last of those is why the reflog is in the question. `--reflog --not <sha>` is what
    survives a `reset --hard`, and the restore-to-innocence shape is otherwise the one
    thing a HEAD comparison alone cannot see. A round that also expired the reflog would
    get past it, and that is stated rather than fixed: the next rung down is always
    reachable, and the honest place to stop is where each rung costs the round a more
    deliberate act than the last. Deleting the stash outright is the far end of that
    ladder, and it is the one shape here reported as its own caveat.

    The final half is deliberately narrow. A moved `origin/main` is not evidence of
    anything — other people push to it while a round runs, which is the normal state of a
    shared repository. What is evidence is a move *during a round that was making commits
    of its own*, and that pairing is the only thing reported. Even then it is worded as
    what it is — a coincidence that cannot be ruled out — because the object a push
    created lives on the server, and nothing local can settle it without a fetch this is
    not going to perform mid-seal.
    """
    if project is None or not project.pinned or project.git_dir is None:
        return ()
    caveats = []

    if not project.git_dir.is_dir():
        # Everything below reads through the stash, so its absence is not a quiet
        # degradation to "clean" — it is the one move that turns every other arm off.
        return (
            f"{SELF_TOUCHED}the git directory paddock stashed beside the pin is gone, so "
            f"nothing here can say what the round did to the toolchain it was measured on",
        )

    fence = project.path / ".git"
    standing = fence.is_file() and fence.read_text(encoding="utf-8") == FENCE_GITFILE
    if not standing:
        # Only reachable deliberately: the fence is a file the round has no reason to
        # open, and replacing it is how a `git init` announces itself.
        caveats.append(
            f"{SELF_TOUCHED}the round made the toolchain a git repository again — the "
            f"fence it was pinned behind is gone"
        )

    edited = [
        line for line in read(project, "status", "--porcelain").stdout.splitlines() if line
    ]
    if edited:
        # The one people underrate: an edit inside a tree that gets deleted looks harmless,
        # but the round spent the rest of its hours running the edited code. Whatever the
        # scorecard says, it is not a measurement of the sha in the ledger.
        caveats.append(
            f"{SELF_TOUCHED}the round edited {len(edited)} file(s) of the toolchain it was "
            f"being measured on, so the code it ran is not the sha in this ledger"
        )

    at = read(project, "rev-parse", "HEAD").stdout.strip()
    head_moved = bool(at) and at != project.head
    if head_moved:
        caveats.append(
            f"{SELF_TOUCHED}the round moved the pin's HEAD from {project.head[:12]} to "
            f"{at[:12]} — it committed into the toolchain through the git directory "
            f"stashed beside it"
        )

    now = _pairs(read(project, *_REF_FORMAT))
    appeared = sorted(set(now) - set(project.pin_refs))
    if appeared:
        caveats.append(
            f"{SELF_TOUCHED}the round put {', '.join(ref for ref, _ in appeared)} in the "
            f"pin, which was cloned with the refs it was pinned at and nothing else"
        )

    # Survives the `reset --hard` that puts HEAD and every ref back where they were: the
    # objects the round built stay reachable from the reflog, and nothing else in a pin
    # nobody fetches into can make a commit the pinned sha does not reach.
    orphaned = read(
        project, "rev-list", "--all", "--reflog", "--not", project.head
    ).stdout.split()
    # Only when HEAD is back where it started; otherwise the line above already said it,
    # and two caveats for one act read as two acts.
    if orphaned and not head_moved:
        caveats.append(
            f"{SELF_TOUCHED}the pin holds {len(orphaned)} commit(s) that {project.head[:12]} "
            f"does not reach, so the round built and then unwound something in the "
            f"toolchain it was being measured on"
        )

    if standing:
        return tuple(caveats)
    added = _git("remote", cwd=project.path).stdout.split()
    if added:
        caveats.append(
            f"{SELF_TOUCHED}the round put remote(s) {', '.join(added)} on the repository "
            f"it made, having been pinned to one with none"
        )
    made = _git("rev-list", "--all", cwd=project.path).stdout.split()
    if not made:
        return tuple(caveats)
    was = dict(project.remote_refs)
    moved = [
        f"{ref} {was.get(ref, 'absent')[:12]}..{sha[:12]}"
        for ref, sha in _remote_refs(project.source)
        if was.get(ref) != sha
    ]
    if moved:
        caveats.append(
            f"{SELF_TOUCHED}the round made {len(made)} commit(s) in its pin while the "
            f"source's {', '.join(moved)} moved — a push from the round cannot be ruled "
            f"out from here"
        )
    return tuple(caveats)


def release(project: Project | None) -> None:
    """Delete a pinned clone, and never let that failure end a run.

    The result is already sealed by the time this runs, so a tree that will not go away is
    a disk-space problem to report, not a round to fail. A clone is nothing but its own
    directory — no registration in the source repository to unwind, which is the other
    half of why it replaced the worktree.
    """
    if project is None or not project.pinned:
        return
    shutil.rmtree(project.path, ignore_errors=True)
    if project.git_dir is not None:
        shutil.rmtree(project.git_dir, ignore_errors=True)
    if project.path.exists():
        logger.warning("could not delete the pinned clone at %s", project.path)
