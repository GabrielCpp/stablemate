"""The end of a `--worktree` run: what it removes, what it keeps, and where it says why."""
from __future__ import annotations

import io
import json
import shutil
import subprocess
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from workhorse.cli.offline import print_params
from workhorse.pyflow import run as run_mod
from workhorse.pyflow import worktree as worktree_mod
from workhorse.pyflow.errors import WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    (path / "doc.md").write_text("committed\n")
    _git(path, "add", "doc.md")
    _git(path, "commit", "-q", "-m", "one")
    return path


def _commit(cwd: Path, name: str) -> None:
    (cwd / name).write_text(f"{name}\n")
    _git(cwd, "add", name)
    _git(cwd, "commit", "-q", "-m", name)


def _branch_exists(repo: Path, branch: str) -> bool:
    return subprocess.run(
        ["git", "-C", str(repo), "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        check=False,
    ).returncode == 0


def _cut(tmp_path: Path, branch: str = "run/acme-t") -> tuple[Path, Path]:
    repo = _repo(tmp_path / "acme")
    cut = worktree_mod.add(
        repo_dir=repo, worktree_dir=tmp_path, branch=branch, base_ref="main", dir_name="acme-wt"
    )
    return repo, cut.path


def test_clean_unchanged_worktree_is_removed_with_its_branch(tmp_path):
    repo, path = _cut(tmp_path)

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main")

    assert outcome.action == "removed"
    assert outcome.branch_deleted
    assert outcome.reason == "merged into 'main'"
    assert not path.exists()
    assert not _branch_exists(repo, "run/acme-t")


def test_worktree_whose_commits_were_merged_is_removed_with_its_branch(tmp_path):
    repo, path = _cut(tmp_path)
    _commit(path, "feature.md")
    _git(repo, "merge", "-q", "--no-ff", "-m", "land", "run/acme-t")

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main", repo_dir=repo)

    assert outcome.action == "removed"
    assert outcome.branch_deleted
    assert not path.exists()
    assert not _branch_exists(repo, "run/acme-t")


def test_uncommitted_change_keeps_the_worktree(tmp_path):
    repo, path = _cut(tmp_path)
    (path / "scratch.md").write_text("not committed\n")

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main", repo_dir=repo)

    assert outcome.action == "kept"
    assert outcome.reason == "the worktree has uncommitted changes"
    assert path.is_dir()
    assert _branch_exists(repo, "run/acme-t")


def test_ignored_file_does_not_keep_the_worktree(tmp_path):
    repo, path = _cut(tmp_path)
    (repo / ".git" / "info" / "exclude").write_text("cache/\n")
    (path / "cache").mkdir()
    (path / "cache" / "blob").write_text("ignored\n")

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main", repo_dir=repo)

    assert outcome.action == "removed"


def test_unmerged_unpushed_commit_keeps_the_worktree(tmp_path):
    repo, path = _cut(tmp_path)
    _commit(path, "feature.md")

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main", repo_dir=repo)

    assert outcome.action == "kept"
    assert "neither merged into 'main' nor pushed" in outcome.reason
    assert path.is_dir()
    assert _branch_exists(repo, "run/acme-t")


def test_pushed_branch_removes_the_worktree_but_keeps_the_branch(tmp_path):
    repo, path = _cut(tmp_path)
    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "-q", "--bare", str(remote))
    _git(repo, "remote", "add", "origin", str(remote))
    _commit(path, "feature.md")
    _git(path, "push", "-q", "origin", "run/acme-t")

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main", repo_dir=repo)

    assert outcome.action == "removed"
    assert not outcome.branch_deleted
    assert outcome.reason.startswith("pushed to a remote, not merged into 'main'")
    assert "branch 'run/acme-t' kept" in outcome.reason
    assert not path.exists()
    assert _branch_exists(repo, "run/acme-t")


def test_owning_repo_is_found_from_the_worktree(tmp_path):
    repo, path = _cut(tmp_path)

    outcome = worktree_mod.retire(path=path, branch="run/acme-t", base="main")

    assert outcome.action == "removed"
    assert _git(repo, "worktree", "list").count("\n") == 0


def test_base_name_resolves_head_to_the_checked_out_branch(tmp_path):
    repo = _repo(tmp_path / "acme")

    assert worktree_mod.base_name(repo, "HEAD") == "main"
    assert worktree_mod.base_name(repo, "side") == "side"


SEEN: dict[str, Any] = {}


class Finish(Workflow):
    """Commits in its worktree and, when told to, lands the commit on main the way a finish step would."""

    repo_dir: str = ""
    origin: str = ""
    commit: bool = False
    land: bool = False
    dirty: bool = False
    fail: bool = False
    interrupt: bool = False

    def start(self) -> Transition:
        here = Path(self.repo_dir)
        SEEN["path"] = here
        if self.commit:
            _commit(here, "feature.md")
        if self.land:
            _git(Path(self.origin), "merge", "-q", "--no-ff", "-m", "land", _git(here, "rev-parse", "HEAD"))
        if self.dirty:
            (here / "scratch.md").write_text("left behind\n")
        if self.fail:
            raise WorkflowFailed("the story did not land", failure_class="test-failure")
        if self.interrupt:
            raise KeyboardInterrupt
        return Done(None)


class _Registry(Registry):
    def directory(self) -> Path:
        return Path(__file__).parent


def _registry() -> Registry:
    registry = _Registry("worktree-retire")
    registry.add_flows(main=Finish)
    registry.entry = Finish
    return registry


REGISTRY = _registry()


def _dispatch(tmp_path: Path, **params: Any) -> tuple[int | str | None, dict[str, Any], Path, Path]:
    repo = _repo(tmp_path / "acme")
    worktree_dir = tmp_path / "worktrees"
    worktree_dir.mkdir()
    runs_dir = tmp_path / "runs"
    SEEN.clear()
    with patch.object(run_mod, "resolve_worktree_dir", lambda: worktree_dir):
        try:
            code = run_pyflow(RunInvocation(
                registry=REGISTRY, runs_dir=runs_dir, flow="main", run_id="t", worktree=True,
                params={"repo_dir": str(repo), "origin": str(repo), **params},
            ))
        except SystemExit as exc:
            code = exc.code
    (run_dir,) = [d for d in runs_dir.iterdir() if d.is_dir()]
    return code, json.loads((run_dir / "run.json").read_text()), repo, run_dir


def test_run_that_lands_its_commit_removes_worktree_and_branch(tmp_path):
    code, record, repo, _ = _dispatch(tmp_path, commit=True, land=True)

    assert code == 0
    assert record["terminal"] == "terminal"
    assert record["worktree_base"] == "main"
    assert record["worktree_outcome"]["action"] == "removed"
    assert record["worktree_outcome"]["branch_deleted"] is True
    assert not SEEN["path"].exists()
    assert not _branch_exists(repo, "run/worktree-retire-t")


def test_run_that_leaves_its_commit_unlanded_keeps_the_worktree(tmp_path):
    code, record, repo, _ = _dispatch(tmp_path, commit=True)

    assert code == 0
    assert record["worktree_outcome"]["action"] == "kept"
    assert "neither merged into 'main' nor pushed" in record["worktree_outcome"]["reason"]
    assert SEEN["path"].is_dir()
    assert _branch_exists(repo, "run/worktree-retire-t")


def test_run_that_leaves_uncommitted_changes_keeps_the_worktree(tmp_path):
    code, record, _, _ = _dispatch(tmp_path, dirty=True)

    assert code == 0
    assert record["worktree_outcome"] == {
        "action": "kept", "reason": "the worktree has uncommitted changes", "branch_deleted": False,
    }
    assert SEEN["path"].is_dir()


def test_failed_run_keeps_the_worktree_and_its_terminal(tmp_path):
    code, record, repo, _ = _dispatch(tmp_path, fail=True)

    assert code != 0
    assert record["terminal"] == "fail"
    assert record["worktree_outcome"]["action"] == "kept"
    assert record["worktree_outcome"]["reason"] == "the run failed in 'start'"
    assert record["worktree_path"] == str(SEEN["path"])
    assert SEEN["path"].is_dir()
    assert _branch_exists(repo, "run/worktree-retire-t")


def test_interrupted_run_keeps_the_worktree_for_resume(tmp_path):
    code, record, repo, _ = _dispatch(tmp_path, interrupt=True)

    assert code != 0
    assert record["interrupted_at"]
    assert record["worktree_outcome"]["action"] == "kept"
    assert record["worktree_outcome"]["reason"] == "the run was interrupted in 'start'"
    assert Path(record["worktree_path"]).is_dir()
    assert _branch_exists(repo, "run/worktree-retire-t")


def test_status_params_reports_the_worktree_outcome(tmp_path):
    _, record, _, run_dir = _dispatch(tmp_path, commit=True)

    out = io.StringIO()
    with redirect_stdout(out):
        print_params(run_dir)

    report = json.loads(out.getvalue())
    assert report["worktree"] == {
        "path": record["worktree_path"],
        "branch": "run/worktree-retire-t",
        "base": "main",
        "outcome": record["worktree_outcome"],
    }
