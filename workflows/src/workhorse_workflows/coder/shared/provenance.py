"""Which commits and files belong to a story."""
from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from git.exc import GitError
from ostler.book.sources import story_commits

from workhorse_workflows.coder.shared.blueprint import blueprint
from workhorse_workflows.coder.shared.schemas.dev import (
    ChangedFiles,
)
from workhorse_workflows.kit import open_repo, trunk_base


def _story_trailers(message: str) -> set[str]:
    return {
        line.removeprefix("Story:").strip()
        for line in message.splitlines()
        if line.startswith("Story:")
    }


def trunk_story_base(root: Path, base: str, refs: tuple[str, ...]) -> str:
    """On trunk itself, the parent of this story's earliest commit; elsewhere ``base`` unchanged."""
    repo = open_repo(root)
    if repo.git.rev_parse(base) != repo.git.rev_parse("HEAD"):
        return base
    grep = [f"--grep={ref}" for ref in refs]
    log = repo.git.log("--reverse", "--fixed-strings", *grep, "--format=%x1e%P%x00%B", "HEAD")
    wanted = set(refs)
    for record in log.split("\x1e")[1:]:
        parents, _, message = record.partition("\x00")
        if _story_trailers(message) & wanted and parents.split():
            return parents.split()[0]
    return base


def story_base(root: Path, refs: tuple[str, ...]) -> str:
    """The commit a story's own work is measured from in `root`."""
    return trunk_story_base(root, trunk_base(root), refs)


def _lines(root: Path, *args: str) -> list[str]:
    try:
        done = subprocess.run(
            ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=30
        )
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"git {' '.join(args[:2])} failed in {root}: {exc.stderr.strip()}") from exc
    return [line.strip() for line in done.stdout.splitlines() if line.strip()]


@dataclass(frozen=True)
class StoryChange:
    base: str
    files: tuple[str, ...]
    story: str = ""
    commits: tuple[str, ...] = ()
    among: int = 0
    whole: bool = False

    @property
    def narrowed(self) -> bool:
        return bool(self.commits) and not self.whole

    @property
    def reading(self) -> str:
        if not self.commits:
            return f"the range since {self.base}, no commit carries 'Story: {self.story}'"
        if self.whole:
            return f"story {self.story}: {len(self.commits)} commit(s), the whole range since {self.base}"
        return f"story {self.story}: {len(self.commits)} commit(s) among {self.among} since {self.base}"


def story_change(root: Path, refs: tuple[str, ...]) -> StoryChange:
    """The files a story changed in `root`: its own commits and the uncommitted work, or the range from its base."""
    top = Path(_lines(root, "rev-parse", "--show-toplevel")[0])
    base = story_base(top, refs)
    commits = tuple(dict.fromkeys(c for ref in refs for c in story_commits(str(top), ref)))
    since = _lines(top, "rev-list", "--reverse", "--no-merges", f"{base}..HEAD")
    whole = bool(commits) and set(commits) == set(since)
    found: list[str] = []
    if commits and not whole:
        for commit in commits:
            found += _lines(
                top, "diff-tree", "--no-commit-id", "--no-renames", "-r", "--name-only", "--root", commit
            )
        found += _lines(top, "diff", "--name-only", "--no-renames", "HEAD")
    else:
        found += _lines(top, "diff", "--name-only", "--no-renames", base)
    found += _lines(top, "ls-files", "--others", "--exclude-standard")
    return StoryChange(
        base=base,
        files=tuple(dict.fromkeys(found)),
        story=refs[0] if refs else "",
        commits=commits,
        among=len(since),
        whole=whole,
    )


@blueprint.node
def changed_files(
    logger: logging.Logger, cwd: str = "", story_slug: str = "", story_id: str = ""
) -> ChangedFiles:
    """Which files this story has already written in one service checkout."""
    if not cwd or not Path(cwd).expanduser().is_dir():
        return ChangedFiles()
    refs = tuple(dict.fromkeys(r for r in (story_id, story_slug) if r))
    try:
        change = story_change(Path(cwd).expanduser(), refs)
    except (GitError, ValueError, OSError, subprocess.SubprocessError) as exc:
        logger.info("could not list changed files in %s: %s", cwd, exc)
        return ChangedFiles()
    return ChangedFiles(paths=sorted(set(change.files)))


__all__ = ["StoryChange", "changed_files", "story_base", "story_change", "trunk_story_base"]
