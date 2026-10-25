"""The trial tree: one repo or a folder of them, and the launch a workflow in it is given."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import tomli_w
from fakes import DOCS, PRODUCTS, STORY, fake_run, folder_run

from paddock.tasks import stablemate as sm
from paddock.tasks import tree
from paddock.tasks.stablemate import TrialError


def test_a_single_repo_has_no_members_and_a_folder_names_its_children(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    assert tree.members(run.stage) == tuple(sorted((*PRODUCTS, DOCS)))
    assert tree.stage_members(run) == tuple(sorted((*PRODUCTS, DOCS)))
    single = tmp_path / "single"
    (single / ".git").mkdir(parents=True)
    assert tree.members(single) == ()
    assert tree.repos_at(single, ()) == {"": single}
    assert tree.repos_at(run.stage, ("web-app",)) == {"web-app": run.stage / "web-app"}


def test_a_single_repo_launches_exactly_as_before(tmp_path: Path) -> None:
    run = fake_run(tmp_path)
    launch = tree.launch(run, run.stage)
    assert launch.workspace == ""
    assert launch.repo_dir == run.stage
    assert launch.env == sm.trial_env(run.stage)
    assert launch.flags() == ["--config", str(sm.effective(run))]


def test_the_staged_workspace_is_the_entry_whose_repos_sit_in_the_stage(tmp_path: Path) -> None:
    assert tree.staged_workspace(folder_run(tmp_path)) == "desk"
    assert tree.staged_workspace(fake_run(tmp_path / "single")) == ""


def test_a_folder_with_no_or_several_workspaces_is_refused(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    config = tomllib.loads(run.config.read_text(encoding="utf-8"))
    config["workspaces"]["other"] = list(config["workspaces"]["desk"])
    run.config.write_text(tomli_w.dumps(config), encoding="utf-8")
    with pytest.raises(TrialError, match="found desk, other"):
        tree.staged_workspace(run)
    config["workspaces"] = {"elsewhere": [str(tmp_path / "nowhere")]}
    run.config.write_text(tomli_w.dumps(config), encoding="utf-8")
    with pytest.raises(TrialError, match="found none"):
        tree.staged_workspace(run)


def test_the_trial_config_points_the_workspace_and_docs_into_the_trial_tree(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    root = tmp_path / "trial" / "tree"
    config = tomllib.loads(tree.trial_config(run, root).read_text(encoding="utf-8"))
    assert tree.trial_config(run, root) == root.with_name("tree.stablemate-config.toml")
    assert config["artifacts_dir"] == str(root / DOCS)
    assert config["workspaces"]["desk"] == [str(root / name) for name in PRODUCTS]


def test_a_folder_launch_carries_the_workspace_and_the_docs_home(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    root = tmp_path / "trial" / "tree"
    launch = tree.launch(run, root)
    assert launch.workspace == "desk"
    assert launch.repo_dir == root / DOCS
    assert launch.env["STABLEMATE_ARTIFACTS_DIR"] == str(root / DOCS)
    assert launch.flags() == ["--config", str(launch.config), "--workspace", "desk"]
    assert tomllib.loads(launch.config.read_text(encoding="utf-8"))["workspaces"]["desk"] == [
        str(root / name) for name in PRODUCTS
    ]


def test_a_folder_spec_dir_is_found_under_the_docs_home(tmp_path: Path) -> None:
    run = folder_run(tmp_path)
    assert tree.spec_dir(run, run.stage, STORY) == run.stage / DOCS / "specs" / STORY
