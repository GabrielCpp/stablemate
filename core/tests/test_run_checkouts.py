"""The folders a run works in: the branch rule that maps a run's branch to a worktree of each repository."""

from __future__ import annotations

import subprocess

import pytest

from stablemate_core import config as cfgmod

BRANCH = "run/coder-t"


def _git(folder, *args):
    subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True)


def _out(folder, *args):
    done = subprocess.run(["git", "-C", str(folder), *args], check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _repo(path):
    path.mkdir(parents=True)
    _git(path, "init", "--quiet", "-b", "main")
    _git(path, "-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "--allow-empty", "-m", "x", "--quiet")
    return path.resolve()


def _tree(repo, where, branch=BRANCH):
    target = where / f"{repo.name}-{branch.replace('/', '-')}"
    _git(repo, "worktree", "add", "-q", "-b", branch, str(target))
    return target.resolve()


@pytest.fixture
def world(tmp_path, monkeypatch, cfg_file):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))
    artifacts = _repo(tmp_path / "artifacts")
    api = _repo(tmp_path / "api")
    web = _repo(tmp_path / "web")
    cfg_file.write_text(
        f'[workspaces]\nacme = [{{ path = "{api}", name = "api" }}, {{ path = "{web}", name = "web" }}]\n'
    )
    return {"artifacts": artifacts, "api": api, "web": web, "trees": tmp_path / "trees"}


def test_docs_home_is_the_artifacts_main_folder_from_an_artifacts_worktree(world):
    tree = _tree(world["artifacts"], world["trees"])

    assert cfgmod.docs_home(tree) == world["artifacts"]


def test_workspace_checkouts_maps_each_member_to_its_worktree_on_the_run_branch_and_others_to_their_folder(world):
    api = _tree(world["api"], world["trees"])

    assert cfgmod.workspace_checkouts(api) == {"api": api, "web": world["web"]}


def test_workspace_checkouts_from_a_main_checkout_is_workspace_members(world):
    _tree(world["api"], world["trees"])

    assert cfgmod.workspace_checkouts(world["api"]) == cfgmod.workspace_members()


def test_a_detached_linked_worktree_gets_no_branch_rule(world):
    api = _tree(world["api"], world["trees"])
    _tree(world["web"], world["trees"])
    _git(api, "checkout", "-q", "--detach")

    assert cfgmod.run_branch(api) is None
    assert cfgmod.workspace_checkouts(api) == cfgmod.workspace_members()


def test_a_linked_worktree_of_an_unrelated_repository_gets_no_branch_rule(world, tmp_path):
    other = _repo(tmp_path / "other")
    tree = _tree(other, world["trees"])

    assert cfgmod.run_branch(tree) is None


def test_run_workspace_names_the_one_workspace_holding_the_member(world):
    assert cfgmod.run_workspace(world["api"]) == "acme"
    assert cfgmod.run_workspace(_tree(world["api"], world["trees"])) == "acme"


def test_run_workspace_of_a_member_in_two_workspaces_names_the_flag(world, cfg_file):
    api = world["api"]
    cfg_file.write_text(f'[workspaces]\nacme = ["{api}"]\nglobex = ["{api}"]\n')

    with pytest.raises(ValueError, match="--workspace"):
        cfgmod.run_workspace(api)
    assert cfgmod.run_workspace(api, "globex") == "globex"


def test_run_workspace_from_the_artifacts_repo_with_one_workspace_is_that_one(world):
    assert cfgmod.run_workspace(world["artifacts"]) == "acme"


def test_run_workspace_of_a_repository_in_none_is_empty(world, tmp_path):
    assert cfgmod.run_workspace(_repo(tmp_path / "other")) == ""


def test_ensure_artifacts_repo_makes_a_first_commit_holding_only_the_gitignore(tmp_path, monkeypatch):
    target = tmp_path / "artifacts"
    target.mkdir()
    (target / "services.py").write_text("x = 1\n")
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(target))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "nogit"))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(tmp_path / "nogit"))

    root = cfgmod.ensure_artifacts_repo()

    assert _out(root, "ls-tree", "-r", "--name-only", "HEAD") == ".gitignore"
    _git(root, "worktree", "add", "-q", "-b", BRANCH, str(tmp_path / "tree"))


def test_ensure_artifacts_repo_commits_once(tmp_path, monkeypatch):
    monkeypatch.setenv(cfgmod.ARTIFACTS_DIR_ENV, str(tmp_path / "artifacts"))

    root = cfgmod.ensure_artifacts_repo()
    cfgmod.ensure_artifacts_repo()

    assert _out(root, "rev-list", "--count", "HEAD") == "1"
