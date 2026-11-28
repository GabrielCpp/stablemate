from __future__ import annotations

from git import Repo


def stage_paths(repo: Repo, *pathspecs: str) -> None:
    """Stage the files ``pathspecs`` name that git can stage. A tracked file is staged even under an ignored folder, which a plain add refuses."""
    present = [spec for spec in pathspecs if _matches(repo, spec)]
    tracked = [spec for spec in present if repo.git.ls_files("--cached", "--", spec).strip()]
    untracked = [spec for spec in present if spec not in tracked]
    if tracked:
        repo.git.add("--force", "--", *tracked)
    if untracked:
        repo.git.add("--", *untracked)


def staged_or_tracked(repo: Repo, spec: str) -> bool:
    """Does git know ``spec`` after staging: an index entry, or a deletion staged against HEAD."""
    return bool(
        repo.git.ls_files("--cached", "--", spec).strip() or repo.git.diff("--cached", "--name-only", "--", spec).strip()
    )


def _matches(repo: Repo, spec: str) -> bool:
    """Does ``spec`` name a file git can stage: one in the index or one untracked and not ignored. A deletion already staged names neither, and the commit's pathspec carries it."""
    return bool(repo.git.ls_files("--cached", "--others", "--exclude-standard", "--", spec).strip())
