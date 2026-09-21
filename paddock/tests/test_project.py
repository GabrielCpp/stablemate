"""Pinning the project a round drives: the clone, its missing remotes, the fallbacks."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from paddock import project as project_mod

from tests.test_runner import run


def head_of(repo: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.strip()


def test_a_pin_is_a_detached_checkout_at_the_sources_head(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert pinned.pinned and pinned.path != repo
    assert pinned.head == head_of(repo)
    assert project_mod.read(pinned, "rev-parse", "HEAD").stdout.strip() == pinned.head
    project_mod.release(pinned)
    assert not pinned.path.exists()


def test_the_pin_excludes_the_checkouts_uncommitted_edits(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert pinned.dirty
    assert (pinned.path / "README.md").read_text(encoding="utf-8") == "acme\n"
    project_mod.release(pinned)


def test_pinning_twice_over_the_same_work_dir_succeeds(repo: Path, tmp_path: Path) -> None:
    first = project_mod.pin(repo, work=tmp_path / "work")
    second = project_mod.pin(repo, work=tmp_path / "work")
    assert second is not None and second.pinned
    assert first is not None and second.path == first.path
    project_mod.release(second)


def test_a_pin_has_no_remote_to_push_to(repo: Path, tmp_path: Path) -> None:
    """The whole reason the pin is a clone and not a worktree."""
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/acme.git"],
        cwd=str(repo), check=True,
    )

    pinned = project_mod.pin(repo, work=tmp_path / "work")

    assert pinned is not None and pinned.pinned
    assert project_mod.read(pinned, "remote").stdout.split() == []
    assert subprocess.run(
        ["git", "remote"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.split() == ["origin"]
    project_mod.release(pinned)


def test_a_pin_carries_the_sources_history_not_just_its_tip(
    repo: Path, tmp_path: Path
) -> None:
    """A shallow pin would break the one check that caught the leak."""
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert project_mod.read(pinned, "rev-parse", "--is-shallow-repository").stdout.strip() == (
        "false"
    )
    project_mod.release(pinned)


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

task(name="demo", seed="acme", config="configs/test.toml")

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
    assert not driven.exists()


def commit(repo: Path, message: str) -> None:
    (repo / f"{message}.txt").write_text(message, encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run(["git", *args], cwd=str(repo), check=True)


def test_a_quiet_round_escapes_nothing(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert project_mod.escaped(pinned) == ()
    project_mod.release(pinned)


def test_the_toolchain_is_not_a_repository_the_round_can_commit_into(
    repo: Path, tmp_path: Path
) -> None:
    """The fence, from the round's side: git in the pin fails, and says why."""
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    outer = subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "leak"],
        cwd=str(pinned.path), capture_output=True, text=True, check=False,
    )
    assert outer.returncode != 0
    assert "not a git repository" in outer.stderr
    project_mod.release(pinned)


def test_editing_the_toolchain_mid_round_is_a_self_touch(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    (pinned.path / "README.md").write_text("patched mid-round\n", encoding="utf-8")

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "1 file(s)" in caveats[0] and "not the sha in this ledger" in caveats[0]
    project_mod.release(pinned)


def test_a_round_that_rebuilds_the_repository_says_so(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    (pinned.path / ".git").unlink()
    subprocess.run(["git", "init", "-q"], cwd=str(pinned.path), check=True)
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/acme.git"],
        cwd=str(pinned.path), check=True,
    )

    caveats = project_mod.escaped(pinned)

    assert all(c.startswith(project_mod.SELF_TOUCHED) for c in caveats)
    assert any("fence it was pinned behind is gone" in c for c in caveats)
    assert any("origin" in c for c in caveats)
    project_mod.release(pinned)


def test_a_remote_that_moved_under_a_committing_round_cannot_be_ruled_out(
    repo: Path, tmp_path: Path
) -> None:
    upstream = tmp_path / "upstream"
    subprocess.run(["git", "clone", "-q", str(repo), str(upstream)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(upstream)], cwd=str(repo), check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    (pinned.path / ".git").unlink()
    subprocess.run(["git", "init", "-q"], cwd=str(pinned.path), check=True)
    commit(pinned.path, "leaked")
    commit(upstream, "somebody-else")
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    caveats = project_mod.escaped(pinned)

    assert all(c.startswith(project_mod.SELF_TOUCHED) for c in caveats)
    assert any("cannot be ruled out from here" in c for c in caveats)
    project_mod.release(pinned)


def test_a_moving_remote_alone_is_somebody_elses_work(repo: Path, tmp_path: Path) -> None:
    upstream = tmp_path / "upstream"
    subprocess.run(["git", "clone", "-q", str(repo), str(upstream)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(upstream)], cwd=str(repo), check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    pinned = project_mod.pin(repo, work=tmp_path / "work")
    commit(upstream, "somebody-else")
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    assert project_mod.escaped(pinned) == ()
    project_mod.release(pinned)


def test_a_pin_that_was_asked_for_and_not_made_is_a_caveat(repo: Path, tmp_path: Path) -> None:
    """The promise, not the escape."""
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    degraded = project_mod.pin(not_a_repo, work=tmp_path / "work")
    assert degraded is not None and not degraded.pinned

    caveats = project_mod.degraded(degraded, requested=True)
    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.UNPINNED)
    assert str(not_a_repo) in caveats[0]


def test_a_deliberate_opt_out_is_not_caveated(repo: Path, tmp_path: Path) -> None:
    """`--no-pin-project` is a decision, and `pinned: false` in the ledger keeps it answerable."""
    off = project_mod.pin(repo, work=tmp_path / "work", enabled=False)
    assert project_mod.degraded(off, requested=False) == ()
    assert project_mod.degraded(None, requested=True) == ()


def test_a_pin_that_was_made_says_nothing(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None and pinned.pinned
    assert project_mod.degraded(pinned, requested=True) == ()


def test_an_unpinned_run_is_not_asked(repo: Path, tmp_path: Path) -> None:
    unpinned = project_mod.pin(repo, work=tmp_path / "work", enabled=False)
    assert project_mod.escaped(unpinned) == ()
    assert project_mod.escaped(None) == ()




def stash_git(pinned: project_mod.Project, *args: str) -> None:
    subprocess.run(
        ["git", "--git-dir", str(pinned.git_dir), "--work-tree", str(pinned.path), *args],
        cwd=str(pinned.path), check=True,
    )


def test_a_round_that_commits_through_the_stashed_git_dir_says_so(
    repo: Path, tmp_path: Path
) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    (pinned.path / "patched.py").write_text("x = 1\n", encoding="utf-8")
    stash_git(pinned, "add", "-A")
    stash_git(pinned, "commit", "-q", "-m", "patched the toolchain mid-round")

    assert (pinned.path / ".git").read_text(encoding="utf-8") == project_mod.FENCE_GITFILE
    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "moved the pin's HEAD" in caveats[0]
    project_mod.release(pinned)


def test_a_round_that_unwinds_its_own_commit_still_says_so(repo: Path, tmp_path: Path) -> None:
    """The restore-to-innocence shape: patch, run the patched toolchain for an hour, then `reset --hard` back to the pinned sha so HEAD, the refs and the tree all match again."""
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    (pinned.path / "patched.py").write_text("x = 1\n", encoding="utf-8")
    stash_git(pinned, "add", "-A")
    stash_git(pinned, "commit", "-q", "-m", "patched")
    stash_git(pinned, "reset", "-q", "--hard", pinned.head)

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert "does not reach" in caveats[0] and "unwound" in caveats[0]
    project_mod.release(pinned)


def test_a_ref_the_round_made_in_its_pin_says_so(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    stash_git(pinned, "branch", "mine")

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert "refs/heads/mine" in caveats[0]
    project_mod.release(pinned)


def test_a_stash_that_is_gone_is_reported_rather_than_read_as_clean(
    repo: Path, tmp_path: Path
) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None and pinned.git_dir is not None
    shutil.rmtree(pinned.git_dir)

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "nothing here can say what the round did" in caveats[0]
    project_mod.release(pinned)
