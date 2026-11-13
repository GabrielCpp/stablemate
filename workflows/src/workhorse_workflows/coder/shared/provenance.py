"""Which commits and files belong to a story."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

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


@blueprint.node
def changed_files(
    logger: logging.Logger, cwd: str = "", story_slug: str = "", story_id: str = ""
) -> ChangedFiles:
    """Which files this story has already written in one service checkout."""
    if not cwd or not Path(cwd).expanduser().is_dir():
        return ChangedFiles()
    commands = [["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]]
    if story_slug or story_id:
        greps = [
            f"--grep=Story: {ref}" for ref in dict.fromkeys((story_id, story_slug)) if ref
        ]
        commands.append(["log", "--name-only", "--pretty=format:", *greps])
    found: list[str] = []
    for args in commands:
        try:
            done = subprocess.run(
                ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=30
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.info("could not list changed files in %s: %s", cwd, exc)
            break
        if done.returncode == 0:
            found += [line.strip() for line in done.stdout.splitlines() if line.strip()]
    return ChangedFiles(paths=sorted(set(found)))


__all__ = ["changed_files", "story_base", "trunk_story_base"]
