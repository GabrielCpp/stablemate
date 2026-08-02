"""Worktree checkout: N concurrent runs, one host repo, one working tree each.

The clone model gives each container a disposable copy in its own volume, which it
resets to the remote on every restart. That is wrong for concurrent runs against a
repo the operator actually owns: it costs a full clone per run, it puts each run's
refs in a namespace nobody else can see, and "reset to the remote on restart" means
a restart mid-run throws away work.

Worktrees invert all three — and the three rules that fall out are what these tests
pin:

* **detached**, because no workflow knows its branch at checkout time, and claiming
  one here would make the *second* concurrent run fail at checkout;
* **never reset**, because this directory sits on the operator's disk beside their
  own checkout, so a restart is a resume;
* **prune first**, because a registration outlives a directory that was deleted
  without `git worktree remove`, and `worktree add` then refuses the path.

Real git repositories throughout — worktree registration is written on both sides by
absolute path, and a fake would be asserting on the mock rather than on git.

    ./.venv/bin/python -m pytest tests/test_kit_worktree.py
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from workhorse_workflows.kit.workspace import checkout_workspace

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(at: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(at), *args], capture_output=True, text=True, check=True, timeout=30
    ).stdout.strip()


@pytest.fixture
def host_repo(tmp_path: Path) -> Path:
    """A repo standing in for the operator's own checkout, bound into the container."""
    repo = tmp_path / "host" / "api-service"
    repo.mkdir(parents=True)
    _git(repo, "init", "--quiet", "--initial-branch", "main")
    _git(repo, "config", "user.email", "agent@example.com")
    _git(repo, "config", "user.name", "Agent")
    (repo / "README.md").write_text("acme\n")
    _git(repo, "add", "README.md")
    _git(repo, "commit", "--quiet", "-m", "initial")
    return repo


def _checkout(host_repo: Path, root: Path, *, branch: str = "main") -> Path:
    checkout_workspace(
        "",
        root,
        repo_url=str(host_repo),
        repo_name=host_repo.name,
        repo_branch=branch,
        source_mode="worktree",
        worktree_root=str(root),
    )
    return root / host_repo.name


# --------------------------------------------------------------------------- #
# It is a worktree, and it is detached
# --------------------------------------------------------------------------- #


def test_a_run_gets_a_working_tree_of_the_host_repo(host_repo: Path, tmp_path: Path):
    tree = _checkout(host_repo, tmp_path / "worktrees" / "run-1")

    assert (tree / "README.md").read_text() == "acme\n"
    # `.git` is a FILE pointing back into the source repo, not a directory — no
    # second object store, which is the whole cost saving.
    assert (tree / ".git").is_file()
    assert str(host_repo) in (tree / ".git").read_text()


def test_the_worktree_is_detached_so_the_branch_stays_free(host_repo: Path, tmp_path: Path):
    """Claiming `main` here would make the second concurrent run fail at checkout —
    git refuses to check out a branch another worktree holds. The branch is cut later,
    at a workflow node, when the run actually knows what it is."""
    tree = _checkout(host_repo, tmp_path / "worktrees" / "run-1")

    assert _git(tree, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"  # detached
    assert _git(tree, "rev-parse", "HEAD") == _git(host_repo, "rev-parse", "main")


def test_two_concurrent_runs_each_get_their_own_tree_of_one_repo(host_repo: Path, tmp_path: Path):
    """The point of the whole plan. Both trees exist at once, off one object store,
    and neither has claimed a branch from the other."""
    first = _checkout(host_repo, tmp_path / "worktrees" / "run-1")
    second = _checkout(host_repo, tmp_path / "worktrees" / "run-2")

    assert first.exists() and second.exists()
    assert first != second
    registered = _git(host_repo, "worktree", "list")
    assert str(first) in registered
    assert str(second) in registered


def test_each_tree_works_independently(host_repo: Path, tmp_path: Path):
    """Two runs editing at once must not see each other's working files."""
    first = _checkout(host_repo, tmp_path / "worktrees" / "run-1")
    second = _checkout(host_repo, tmp_path / "worktrees" / "run-2")

    (first / "only-in-first.txt").write_text("x\n")
    assert not (second / "only-in-first.txt").exists()


# --------------------------------------------------------------------------- #
# Resume: never reset what the operator may be mid-way through
# --------------------------------------------------------------------------- #


def test_an_existing_worktree_is_left_exactly_as_it_is(host_repo: Path, tmp_path: Path):
    """`docker restart` re-runs the checkout. Unlike a clone in a disposable volume,
    this directory holds real work — resetting it is data loss, so a second checkout
    is a no-op."""
    root = tmp_path / "worktrees" / "run-1"
    tree = _checkout(host_repo, root)
    (tree / "work-in-progress.txt").write_text("half a story\n")
    _git(tree, "add", "work-in-progress.txt")
    _git(tree, "commit", "--quiet", "-m", "wip")
    head = _git(tree, "rev-parse", "HEAD")

    _checkout(host_repo, root)  # the restart

    assert (tree / "work-in-progress.txt").read_text() == "half a story\n"
    assert _git(tree, "rev-parse", "HEAD") == head


def test_uncommitted_work_survives_a_restart_too(host_repo: Path, tmp_path: Path):
    root = tmp_path / "worktrees" / "run-1"
    tree = _checkout(host_repo, root)
    (tree / "README.md").write_text("edited by a blocked gate\n")

    _checkout(host_repo, root)

    assert (tree / "README.md").read_text() == "edited by a blocked gate\n"


def test_a_branch_cut_inside_the_worktree_is_not_undone_by_a_restart(host_repo, tmp_path):
    """The branch arrives later, at a workflow node. A restart must not detach it
    again — that would orphan whatever the run had committed to it."""
    root = tmp_path / "worktrees" / "run-1"
    tree = _checkout(host_repo, root)
    _git(tree, "checkout", "--quiet", "-b", "feat/acme-1")

    _checkout(host_repo, root)

    assert _git(tree, "rev-parse", "--abbrev-ref", "HEAD") == "feat/acme-1"


# --------------------------------------------------------------------------- #
# Stale registrations
# --------------------------------------------------------------------------- #


def test_a_deleted_run_directory_does_not_poison_the_path_forever(host_repo, tmp_path):
    """A container removed with `docker rm` never runs `git worktree remove`, so its
    registration outlives it. Without a prune, reusing that path — which a rerun of
    the same run id does — fails with 'already registered'."""
    root = tmp_path / "worktrees" / "run-1"
    tree = _checkout(host_repo, root)
    shutil.rmtree(tree)

    reborn = _checkout(host_repo, root)

    assert (reborn / "README.md").exists()


def test_pruning_never_touches_a_live_worktree(host_repo: Path, tmp_path: Path):
    """The prune runs on every checkout, so a concurrent run's tree must survive it."""
    live = _checkout(host_repo, tmp_path / "worktrees" / "run-1")
    dead = _checkout(host_repo, tmp_path / "worktrees" / "run-2")
    shutil.rmtree(dead)

    _checkout(host_repo, tmp_path / "worktrees" / "run-3")

    assert live.exists()
    assert str(live) in _git(host_repo, "worktree", "list")


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_a_remote_url_is_refused_with_the_reason(tmp_path: Path):
    """You cannot make a worktree of a URL. Say so, and say what to do instead —
    otherwise it surfaces as git complaining about a directory that does not exist."""
    with pytest.raises(ValueError, match="own host path"):
        checkout_workspace(
            "",
            tmp_path / "trees",
            repo_url="https://example.com/acme/api-service.git",
            repo_name="api-service",
            source_mode="worktree",
        )


def test_an_unknown_source_mode_is_refused_rather_than_defaulted(tmp_path: Path):
    with pytest.raises(ValueError, match="unknown source mode"):
        checkout_workspace("", tmp_path, repo_url="/x", source_mode="symlink")


def test_clone_mode_is_still_the_default(host_repo: Path, tmp_path: Path):
    """Nothing about the single-run container changes; a clone is still a clone."""
    root = tmp_path / "workspace"
    checkout_workspace(
        "", root, repo_url=str(host_repo), repo_name=host_repo.name, repo_branch="main"
    )
    assert (root / host_repo.name / ".git").is_dir()  # a real clone, not a worktree file


# --------------------------------------------------------------------------- #
# The workspace-file path, not just the single-repo fallback
# --------------------------------------------------------------------------- #


def test_every_repo_in_a_workspace_file_gets_its_own_tree(host_repo: Path, tmp_path: Path):
    web = host_repo.parent / "web-app"
    shutil.copytree(host_repo, web)

    manifest = tmp_path / "acme.code-workspace"
    manifest.write_text(
        '{"folders": ['
        f'{{"name": "api-service", "path": ".", "url": "{host_repo}", "branch": "main"}},'
        f'{{"name": "web-app", "path": ".", "url": "{web}", "branch": "main"}},'
        '{"name": "docs", "path": "./docs"}'  # no url — never a checkout
        "]}"
    )
    root = tmp_path / "worktrees" / "run-1"

    checkout_workspace(manifest, root, source_mode="worktree", worktree_root=str(root))

    assert (root / "api-service" / ".git").is_file()
    assert (root / "web-app" / ".git").is_file()
    assert not (root / "docs").exists()
