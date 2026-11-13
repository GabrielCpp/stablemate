"""`workhorse run --worktree` in a workspace: one worktree per repository, all on one branch."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from workhorse._vendor.stablemate_core import config as core_config
from workhorse.pyflow import run as run_mod
from workhorse.pyflow import workspace_worktrees
from workhorse.pyflow.errors import WorkflowFailed
from workhorse.pyflow.registry import Registry
from workhorse.pyflow.run import RunInvocation, run_pyflow
from workhorse.pyflow.transitions import Done, Transition
from workhorse.pyflow.workflow import Workflow

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")

BRANCH = "run/wt-ws-t"
SEEN: dict[str, Any] = {}


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _repo(path: Path, *, commit: bool = True) -> Path:
    path.mkdir(parents=True)
    _git(path, "init", "-q", "-b", "main")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    if commit:
        (path / "doc.md").write_text("committed\n")
        _git(path, "add", "doc.md")
        _git(path, "commit", "-q", "-m", "one")
    return path.resolve()


class _Registry(Registry):
    def directory(self) -> Path:
        return Path(__file__).parent


class Observe(Workflow):
    """A one-state flow that notes the folders its run owns while it still owns them."""

    repo_dir: str = ""
    workspace: str = ""

    def start(self) -> Transition:
        SEEN["repo_dir"] = self.repo_dir
        SEEN["trees"] = {
            name: str(core_config.checkout_on(Path(repo), BRANCH)) for name, repo in SEEN["repos"].items()
        }
        SEEN["book_home"] = str(core_config.book_home(Path(self.repo_dir)))
        return Done(None)


REGISTRY = _Registry("wt-ws")
REGISTRY.add_flows(main=Observe)
REGISTRY.entry = Observe


class World:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.api = _repo(root / "api")
        self.web = _repo(root / "web")
        self.artifacts = _repo(root / "artifacts")
        self.trees = root / "trees"
        self.trees.mkdir()
        self.runs = root / "runs"

    def tree(self, name: str) -> Path:
        return self.trees / f"{name}-run-wt-ws-t"

    def go(self, params: dict[str, Any], flow: str = "main", **kwargs: Any) -> int:
        SEEN.clear()
        SEEN["repos"] = {"api": str(self.api), "web": str(self.web), "artifacts": str(self.artifacts)}
        with patch.object(run_mod, "resolve_worktree_dir", lambda: self.trees):
            return run_pyflow(
                RunInvocation(registry=REGISTRY, runs_dir=self.runs, flow=flow, run_id="t", params=params,
                              worktree=True, **kwargs)
            )

    def record(self) -> dict[str, Any]:
        (run_dir,) = [d for d in self.runs.iterdir() if d.is_dir()]
        return json.loads((run_dir / "run.json").read_text())


@pytest.fixture
def world(tmp_path, monkeypatch) -> World:
    built = World(tmp_path)
    config = tmp_path / "home.toml"
    config.write_text(
        f'[workspaces]\nacme = [{{ path = "{built.api}", name = "api" }}, {{ path = "{built.web}", name = "web" }}]\n'
    )
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(config))
    monkeypatch.setenv(core_config.ARTIFACTS_DIR_ENV, str(built.artifacts))
    return built


def test_mode_a_cuts_the_member_the_artifacts_repo_and_the_other_member_on_one_branch(world):
    code = world.go({"repo_dir": str(world.api)})

    assert code == 0
    assert SEEN["trees"] == {name: str(world.tree(name)) for name in ("api", "web", "artifacts")}
    assert SEEN["repo_dir"] == str(world.tree("api"))
    assert SEEN["book_home"] == str(world.tree("artifacts"))
    record = world.record()
    assert [(e["name"], e["branch"], e["books"]) for e in record["worktrees"]] == [
        ("api", BRANCH, False), ("artifacts", BRANCH, True), ("web", BRANCH, False),
    ]
    assert record["worktree_path"] == str(world.tree("api"))


def test_mode_b_points_repo_dir_at_the_artifacts_worktree_and_cuts_every_member(world):
    code = world.go({"repo_dir": str(world.artifacts), "workspace": "acme"})

    assert code == 0
    assert SEEN["repo_dir"] == str(world.tree("artifacts"))
    assert SEEN["trees"]["api"] == str(world.tree("api"))
    assert SEEN["trees"]["web"] == str(world.tree("web"))
    record = world.record()
    assert [(e["name"], e["books"]) for e in record["worktrees"]] == [
        ("artifacts", True), ("api", False), ("web", False),
    ]


def test_a_member_in_two_workspaces_without_the_flag_exits_1_naming_it(world, tmp_path, capsys):
    config = tmp_path / "home.toml"
    config.write_text(f'[workspaces]\nacme = ["{world.api}"]\nglobex = ["{world.api}"]\n')

    code = world.go({"repo_dir": str(world.api)})

    assert code == 1
    assert "--workspace" in capsys.readouterr().out
    assert not list(world.trees.iterdir())


def test_a_failure_cutting_a_later_worktree_removes_the_ones_already_cut(world, capsys):
    _git(world.web, "branch", BRANCH)

    code = world.go({"repo_dir": str(world.api)})

    assert code == 1
    assert "web" in capsys.readouterr().out
    assert not list(world.trees.iterdir())
    for repo in (world.api, world.artifacts):
        assert BRANCH not in _git(repo, "branch", "--list")


def test_cut_removes_what_it_cut_when_a_later_add_fails(world):
    planned, _ = workspace_worktrees.plan(
        repo_dir=world.api, workspace="", worktree_dir=world.trees, sanitized="run-wt-ws-t", base_ref="HEAD"
    )
    real = workspace_worktrees.worktree_mod.add

    def flaky(**kwargs: Any) -> Any:
        if kwargs["repo_dir"] == world.web:
            raise workspace_worktrees.WorktreeError("no room")
        return real(**kwargs)

    with patch.object(workspace_worktrees.worktree_mod, "add", flaky):
        with pytest.raises(workspace_worktrees.WorktreeError, match="no room.*removed"):
            workspace_worktrees.cut(planned, BRANCH)

    assert not list(world.trees.iterdir())
    for repo in (world.api, world.artifacts, world.web):
        assert BRANCH not in _git(repo, "branch", "--list")


def test_dry_run_prints_every_worktree_and_cuts_nothing(world, capsys):
    world.go({"repo_dir": str(world.api)}, dry_run=True)

    out = capsys.readouterr().out
    assert out.count("would cut branch") == 3
    assert not list(world.trees.iterdir())


def test_a_run_outside_any_workspace_still_cuts_one_worktree(world, tmp_path, monkeypatch):
    monkeypatch.setenv(core_config.CONFIG_PATH_ENV, str(tmp_path / "none.toml"))
    solo = _repo(tmp_path / "solo")

    code = world.go({"repo_dir": str(solo)})

    assert code == 0
    record = world.record()
    assert len(record["worktrees"]) == 1
    assert record["worktree_path"] == str(world.trees / "solo-run-wt-ws-t")
    assert record["worktrees"][0]["path"] == record["worktree_path"]


def test_an_unborn_artifacts_repo_gets_its_first_commit_before_the_cut(world):
    shutil.rmtree(world.artifacts)
    world.artifacts.mkdir()
    _git(world.artifacts, "init", "-q", "-b", "main")

    code = world.go({"repo_dir": str(world.api)})

    assert code == 0
    assert SEEN["trees"]["artifacts"] == str(world.tree("artifacts"))


class Writes(Workflow):
    """A flow that commits one book file in the artifacts worktree of its run."""

    repo_dir: str = ""
    workspace: str = ""

    def start(self) -> Transition:
        book = core_config.book_home(Path(self.repo_dir))
        assert book is not None
        (book / "services").mkdir()
        (book / "services" / "api.py").write_text("x = 1\n")
        _git(book, "add", "services/api.py")
        _git(book, "commit", "-q", "-m", "book")
        return Done(None)


class Dies(Workflow):
    repo_dir: str = ""

    def start(self) -> Transition:
        if self.repo_dir:
            raise WorkflowFailed("boom")
        return Done(None)


class Interrupts(Workflow):
    repo_dir: str = ""

    def start(self) -> Transition:
        if self.repo_dir:
            raise KeyboardInterrupt
        return Done(None)


REGISTRY.add_flows(writes=Writes, dies=Dies, interrupts=Interrupts)


def _trees_gone(world: World) -> bool:
    return not any(world.trees.iterdir())


def test_mode_a_success_lands_the_books_and_retires_the_untouched_member(world):
    code = world.go({"repo_dir": str(world.api)}, flow="writes")

    assert code == 0
    assert (world.artifacts / "services" / "api.py").read_text() == "x = 1\n"
    assert _trees_gone(world)
    assert BRANCH not in _git(world.web, "branch", "--list")
    record = world.record()
    outcomes = {e["name"]: e["outcome"]["action"] for e in record["worktrees"]}
    assert outcomes == {"api": "removed", "artifacts": "removed", "web": "removed"}
    assert [e["landing"]["action"] for e in record["worktrees"] if e["landing"]] == ["landed"]


def test_mode_b_success_lands_the_books(world):
    code = world.go({"repo_dir": str(world.artifacts), "workspace": "acme"}, flow="writes")

    assert code == 0
    assert (world.artifacts / "services" / "api.py").is_file()
    assert _trees_gone(world)


def test_a_failed_run_lands_nothing_and_keeps_every_worktree(world):
    before = _git(world.artifacts, "rev-parse", "main")

    code = world.go({"repo_dir": str(world.api)}, flow="dies")

    assert code != 0
    assert _git(world.artifacts, "rev-parse", "main") == before
    record = world.record()
    assert {e["outcome"]["action"] for e in record["worktrees"]} == {"kept"}
    assert len(record["worktrees"]) == 3
    assert all(Path(e["path"]).is_dir() for e in record["worktrees"])


def test_an_interrupted_run_keeps_every_worktree(world):
    with pytest.raises(SystemExit):
        world.go({"repo_dir": str(world.api)}, flow="interrupts")

    record = world.record()
    assert {e["outcome"]["action"] for e in record["worktrees"]} == {"kept"}
    assert all(Path(e["path"]).is_dir() for e in record["worktrees"])
