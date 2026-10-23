"""A follow-up's own follow-ups land in the backlog as a commit, so the story's tree stays clean."""
from __future__ import annotations

import logging
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from ostler import Ostler, doctor
from ostler.model import load
from workhorse.pyflow.blueprint import node_spec
from workhorse_workflows.coder.shared.backlog import file_follow_up_backlog, prune_fix_item, seed_fix_story
from workhorse_workflows.coder.shared.story_commit import check_repos_clean


def test_the_filer_is_a_node_a_flow_can_call() -> None:
    assert node_spec(file_follow_up_backlog)


def test_the_filed_follow_ups_are_committed_and_leave_the_tree_clean(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    write(repo / "docs" / "backlog.md", "# Backlog\n\n## Filed by coder\n")
    git(repo, "add", "docs/backlog.md")
    git(repo, "commit", "-qm", "seed the backlog")

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[{"title": "Clear the cache on sign-out", "reason": "the slice works without it"}],
        repo_dir=str(repo),
    )

    assert drained.appended == 1, drained
    assert "Clear the cache on sign-out" in (repo / "docs" / "backlog.md").read_text(encoding="utf-8")
    subject = git(repo, "log", "-1", "--format=%s").stdout.strip()
    assert subject == "chore(acme): file the deferred follow-ups of acme-story", subject
    assert check_repos_clean(logger, story_slug="acme-story", repo_dir=str(repo)).clean is True


def test_nothing_filed_commits_nothing(
    repo: Path,
    logger: logging.Logger,
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = git(repo, "rev-parse", "HEAD").stdout

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[{"title": "", "reason": "no title"}], repo_dir=str(repo)
    )

    assert drained.appended == 0, drained
    assert git(repo, "rev-parse", "HEAD").stdout == head


HAND_FILED = (
    "# Backlog\n\n## Filed by coder\n\n"
    "- [clear-report-snapshots-on-sign-out] Sign-out leaves the saved report snapshots in the browser.\n"
)


def _seeded(repo: Path, write: Callable[[Path, str], Path], git: Callable[..., subprocess.CompletedProcess]) -> str:
    write(repo / "docs" / "backlog.md", HAND_FILED)
    git(repo, "add", "docs/backlog.md")
    git(repo, "commit", "-qm", "seed the backlog")
    return git(repo, "rev-parse", "HEAD").stdout


def test_a_follow_up_that_cites_a_backlog_item_is_not_filed_again(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = _seeded(repo, write, git)

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[
            {
                "title": "Wipe stored snapshots when the user leaves",
                "reason": "It is filed in docs/backlog.md as [clear-report-snapshots-on-sign-out].",
            }
        ],
        repo_dir=str(repo),
    )

    assert drained.appended == 0, drained
    assert (repo / "docs" / "backlog.md").read_text(encoding="utf-8") == HAND_FILED
    assert git(repo, "rev-parse", "HEAD").stdout == head


def test_a_follow_up_one_word_off_a_backlog_id_is_not_filed_again(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    head = _seeded(repo, write, git)

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[{"title": "Clear saved report snapshots on sign-out", "reason": "the slice works without it"}],
        repo_dir=str(repo),
    )

    assert drained.appended == 0, drained
    assert git(repo, "rev-parse", "HEAD").stdout == head


def test_a_follow_up_filed_earlier_under_another_reason_is_not_filed_again(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    _seeded(repo, write, git)
    title = "Return a 404 for an unknown report"

    first = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[{"title": title, "reason": "today it answers 400"}], repo_dir=str(repo)
    )
    again = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[{"title": title, "reason": "a missing report answers 400 today"}],
        repo_dir=str(repo),
    )

    assert first.appended == 1, first
    assert again.appended == 0, again
    assert (repo / "docs" / "backlog.md").read_text(encoding="utf-8").count(title) == 1


def test_a_batch_files_a_repeated_follow_up_once_and_a_distinct_one_still(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    _seeded(repo, write, git)

    drained = file_follow_up_backlog(
        logger,
        parent="acme-story",
        follow_ups=[
            {"title": "Paginate the report list", "reason": "long lists load slowly"},
            {"title": "Paginate the report list", "reason": "a long list is slow to load"},
            {"title": "Clear the export cache on sign-in", "reason": "a stale export can show"},
        ],
        repo_dir=str(repo),
    )

    assert drained.appended == 2, drained
    text = (repo / "docs" / "backlog.md").read_text(encoding="utf-8")
    assert text.count("Paginate the report list") == 1
    assert "Clear the export cache on sign-in" in text


def test_a_bookkeeping_commit_is_not_refused_by_the_repository_hooks(
    repo: Path,
    logger: logging.Logger,
    write: Callable[[Path, str], Path],
    git: Callable[..., subprocess.CompletedProcess],
) -> None:
    """A hook that judges the whole working tree, such as a rendered-skill drift check, has nothing to say about the one backlog line the workflow wrote, and a refusal would end the run."""
    write(repo / "docs" / "backlog.md", "# Backlog\n\n## Filed by coder\n\n- [acme-cache] Clear the cache on sign-out\n")
    git(repo, "add", "docs/backlog.md")
    git(repo, "commit", "-qm", "seed the backlog")
    hook = repo / git(repo, "rev-parse", "--git-path", "hooks/pre-commit").stdout.strip()
    hook.parent.mkdir(parents=True, exist_ok=True)
    write(hook, f"#!{sys.executable}\nimport sys\nsys.exit(1)\n")
    hook.chmod(0o755)

    drained = file_follow_up_backlog(
        logger, parent="acme-story", follow_ups=[{"title": "Warm the cache", "reason": ""}], repo_dir=str(repo)
    )
    pruned = prune_fix_item(logger, bullet_id="acme-cache", repo_dir=str(repo))

    assert drained.appended == 1, drained
    assert pruned.pruned is True, pruned
    subjects = git(repo, "log", "--format=%s").stdout.splitlines()
    assert subjects[:2] == ["chore(acme): drop shipped fix acme-cache", "chore(acme): file the deferred follow-ups of acme-story"], subjects
    assert check_repos_clean(logger, story_slug="acme-story", repo_dir=str(repo)).clean is True


def test_the_fixes_bucket_the_coder_creates_needs_no_milestone(
    repo: Path,
    logger: logging.Logger,
) -> None:
    assert Ostler(repo).create_milestone("mvp", "MVP").ok

    seeded = seed_fix_story(
        logger, bullet_id="acme-cache", bullet_text="Clear the cache on sign-out", repo_dir=str(repo)
    )

    graph = load(repo)
    bucket = next(epic for epic in graph.epics if epic.name == seeded.epic)
    assert bucket.followups is True
    unowned = [f.ref for f in doctor.run(graph).findings if f.code == "epic-without-milestone"]
    assert unowned == [], unowned
