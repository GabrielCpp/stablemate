"""Pinning the project a round drives: the worktree, the ledger entry, the fallbacks."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from paddock import project as project_mod

from tests.test_runner import run


def head_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()


def test_a_pin_is_a_detached_worktree_at_the_checkouts_head(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert pinned.pinned and pinned.path != repo
    assert pinned.head == head_of(repo)
    assert head_of(pinned.path) == pinned.head
    project_mod.release(pinned)
    assert not pinned.path.exists()


def test_the_pin_excludes_the_checkouts_uncommitted_edits(repo: Path, tmp_path: Path) -> None:
    # The `repo` fixture leaves README.md edited but uncommitted. A round measures
    # committed state, so the worktree must carry the committed text — and say it saw a
    # dirty source, because that is the difference a reader needs to know about.
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert pinned.dirty
    assert (pinned.path / "README.md").read_text(encoding="utf-8") == "acme\n"
    project_mod.release(pinned)


def test_pinning_twice_over_the_same_work_dir_succeeds(repo: Path, tmp_path: Path) -> None:
    # Re-running a label reuses its work directory, and a stale worktree registration
    # there would otherwise fail `git worktree add` with "already registered".
    first = project_mod.pin(repo, work=tmp_path / "work")
    second = project_mod.pin(repo, work=tmp_path / "work")
    assert second is not None and second.pinned
    assert first is not None and second.path == first.path
    project_mod.release(second)


def test_a_source_that_is_not_a_repo_runs_unpinned(tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    unpinned = project_mod.pin(plain, work=tmp_path / "work")
    assert unpinned is not None
    assert not unpinned.pinned and unpinned.path == plain and unpinned.head == ""


def test_disabling_the_pin_still_records_the_head(repo: Path, tmp_path: Path) -> None:
    unpinned = project_mod.pin(repo, work=tmp_path / "work", enabled=False)
    assert unpinned is not None
    assert not unpinned.pinned and unpinned.path == repo
    assert unpinned.head == head_of(repo)


def test_no_project_is_no_pin(tmp_path: Path) -> None:
    assert project_mod.pin(None, work=tmp_path / "work") is None


def test_a_run_drives_the_pinned_tree_and_records_it(
    repo: Path, data_dir: Path, store: Path
) -> None:
    body = '''
from paddock import step, task

task(name="demo", seed="acme", config="benchmarks/configs/test.toml")

@step()
def where(run):
    (run.artifacts / "driven.txt").write_text(str(run.project), encoding="utf-8")
'''
    result = run(repo, data_dir, store, body, project=repo)
    driven = Path((result.stage / "artifacts" / "where" / "driven.txt").read_text(encoding="utf-8"))
    assert driven != repo
    ledger = json.loads((result.stage / "steps.json").read_text(encoding="utf-8"))
    assert ledger["project"]["pinned"] is True
    assert ledger["project"]["head"] == head_of(repo)
    assert ledger["project"]["source"] == str(repo)
    # Released after sealing: the worktree is a per-round cost, not an accumulating one.
    assert not driven.exists()
