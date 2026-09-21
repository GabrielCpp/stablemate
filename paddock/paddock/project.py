"""Pin the project a run drives, so a round measures one state of the code."""

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

    path: Path
    source: Path
    head: str
    pinned: bool
    dirty: bool
    git_dir: Path | None = None
    remote_refs: tuple[tuple[str, str], ...] = ()
    pin_refs: tuple[tuple[str, str], ...] = ()

    def as_json(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "source": str(self.source),
            "head": self.head,
            "pinned": self.pinned,
            "source_dirty": self.dirty,
        }


SELF_TOUCHED = "self-touched: "

UNPINNED = "unpinned: "

FENCE = "the-toolchain-is-off-limits-to-this-round"

FENCE_GITFILE = f"gitdir: ./{FENCE}\n"


def stashed_git_dir(pinned_path: Path) -> Path:
    """Where `fence` put the pin's git directory — the convention, in one place."""
    return pinned_path.parent / "project.git"


def _git(
    *args: str, cwd: Path, git_dir: Path | None = None
) -> subprocess.CompletedProcess[str]:
    where = ["--git-dir", str(git_dir), "--work-tree", str(cwd)] if git_dir else []
    return subprocess.run(
        ["git", *where, *args], cwd=str(cwd), capture_output=True, text=True, check=False
    )


def read(project: Project, *args: str) -> subprocess.CompletedProcess[str]:
    """Run a read-only git command against the pinned tree, fenced or not."""
    return _git(*args, cwd=project.path, git_dir=project.git_dir)


def pin(source: Path | None, *, work: Path, enabled: bool = True) -> Project | None:
    """A remoteless clone of *source*, detached at its HEAD, under *work*."""
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
    shutil.rmtree(dest, ignore_errors=True)
    dest.parent.mkdir(parents=True, exist_ok=True)
    unpinned = Project(
        path=source, source=source, head=sha, pinned=False, dirty=dirty, remote_refs=refs
    )
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


_REF_FORMAT = ("for-each-ref", "--format=%(refname) %(objectname)")


def _pairs(listed: subprocess.CompletedProcess[str]) -> tuple[tuple[str, str], ...]:
    split = (line.split(" ", 1) for line in listed.stdout.splitlines() if " " in line)
    return tuple(sorted((ref, sha) for ref, sha in split))


def _remote_refs(repo: Path) -> tuple[tuple[str, str], ...]:
    return _pairs(_git(*_REF_FORMAT, "refs/remotes", cwd=repo))


def degraded(project: Project | None, *, requested: bool) -> tuple[str, ...]:
    """Whether a pin that was asked for is missing — the promise, not the escape."""
    if project is None or not requested or project.pinned:
        return ()
    return (
        f"{UNPINNED}a pin was asked for and not made, so this round drove {project.path} "
        f"directly — its result is not attributable to the commit the ledger names",
    )


def escaped(project: Project | None) -> tuple[str, ...]:
    """Whether the round reached past its pin — asked while the pin still exists."""
    if project is None or not project.pinned or project.git_dir is None:
        return ()
    caveats = []

    if not project.git_dir.is_dir():
        return (
            f"{SELF_TOUCHED}the git directory paddock stashed beside the pin is gone, so "
            f"nothing here can say what the round did to the toolchain it was measured on",
        )

    fence = project.path / ".git"
    standing = fence.is_file() and fence.read_text(encoding="utf-8") == FENCE_GITFILE
    if not standing:
        caveats.append(
            f"{SELF_TOUCHED}the round made the toolchain a git repository again — the "
            f"fence it was pinned behind is gone"
        )

    edited = [
        line for line in read(project, "status", "--porcelain").stdout.splitlines() if line
    ]
    if edited:
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

    orphaned = read(
        project, "rev-list", "--all", "--reflog", "--not", project.head
    ).stdout.split()
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
    """Delete a pinned clone, and never let that failure end a run."""
    if project is None or not project.pinned:
        return
    shutil.rmtree(project.path, ignore_errors=True)
    if project.git_dir is not None:
        shutil.rmtree(project.git_dir, ignore_errors=True)
    if project.path.exists():
        logger.warning("could not delete the pinned clone at %s", project.path)
