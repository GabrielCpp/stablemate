"""Pinning the project a round drives: the clone, its missing remotes, the fallbacks."""

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


def test_a_pin_is_a_detached_checkout_at_the_sources_head(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert pinned.pinned and pinned.path != repo
    assert pinned.head == head_of(repo)
    assert head_of(pinned.path) == pinned.head
    project_mod.release(pinned)
    assert not pinned.path.exists()


def test_the_pin_excludes_the_checkouts_uncommitted_edits(repo: Path, tmp_path: Path) -> None:
    # The `repo` fixture leaves README.md edited but uncommitted. A round measures
    # committed state, so the pin must carry the committed text — and say it saw a dirty
    # source, because that is the difference a reader needs to know about.
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    assert pinned.dirty
    assert (pinned.path / "README.md").read_text(encoding="utf-8") == "acme\n"
    project_mod.release(pinned)


def test_pinning_twice_over_the_same_work_dir_succeeds(repo: Path, tmp_path: Path) -> None:
    # Re-running a label reuses its work directory, and `git clone` refuses to write
    # into a path that already exists.
    first = project_mod.pin(repo, work=tmp_path / "work")
    second = project_mod.pin(repo, work=tmp_path / "work")
    assert second is not None and second.pinned
    assert first is not None and second.path == first.path
    project_mod.release(second)


def test_a_pin_has_no_remote_to_push_to(repo: Path, tmp_path: Path) -> None:
    """The whole reason the pin is a clone and not a worktree.

    A worktree shares the checkout's `origin`, and one round proved what that costs: an
    agent inside the pinned tree read the toolchain's own AGENTS.md — "push it now, right
    after the commit" — and did, to the public repo. It was obedient, in the wrong
    context. Zero remotes is what turns that into a loud failure the run record keeps,
    and it has to be zero rather than "origin renamed": the gh credential helper is
    machine-wide, so any remote at all is a live route to the network.
    """
    repo_git = subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/acme.git"],
        cwd=str(repo), capture_output=True, text=True, check=False,
    )
    assert repo_git.returncode == 0, repo_git.stderr

    pinned = project_mod.pin(repo, work=tmp_path / "work")

    assert pinned is not None and pinned.pinned
    remotes = subprocess.run(
        ["git", "remote"], cwd=str(pinned.path), capture_output=True, text=True, check=True
    ).stdout.split()
    assert remotes == []
    # And the source keeps the remote it had: the pin is not allowed to edit the operator's
    # checkout on its way to protecting it.
    assert subprocess.run(
        ["git", "remote"], cwd=str(repo), capture_output=True, text=True, check=True
    ).stdout.split() == ["origin"]
    project_mod.release(pinned)


def test_a_pin_carries_the_sources_history_not_just_its_tip(
    repo: Path, tmp_path: Path
) -> None:
    """A shallow pin would break the one check that caught the leak.

    `no_leaks` compares HEAD before and after and lists what is new; a clone without the
    source's history cannot tell a round's commit from an ancestor it simply never had.
    """
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    shallow = subprocess.run(
        ["git", "rev-parse", "--is-shallow-repository"],
        cwd=str(pinned.path), capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert shallow == "false"
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
    # Released after sealing: the clone is a per-round cost, not an accumulating one.
    assert not driven.exists()


def commit(repo: Path, message: str) -> None:
    (repo / f"{message}.txt").write_text(message, encoding="utf-8")
    for args in (["add", "-A"], ["commit", "-q", "-m", message]):
        subprocess.run(["git", *args], cwd=str(repo), check=True)


def test_a_quiet_round_escapes_nothing(repo: Path, tmp_path: Path) -> None:
    # The ordinary case, and the one that has to stay silent: a detector that cried on
    # every round would be read as noise by the third one.
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert project_mod.escaped(pinned) == ()
    project_mod.release(pinned)


def test_a_remote_put_back_on_the_pin_is_a_self_touch(repo: Path, tmp_path: Path) -> None:
    # The pin is handed over with none. Adding one is not something a subject does by
    # accident, and it is the one half of this that is evidence on its own.
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/acme.git"],
        cwd=str(pinned.path), check=True,
    )

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "origin" in caveats[0]
    project_mod.release(pinned)


def test_a_remote_that_moved_under_a_committing_round_cannot_be_ruled_out(
    repo: Path, tmp_path: Path
) -> None:
    # Neither half is evidence alone — a round may commit inside its pin for good
    # reasons, and origin moves all day because other people are working. The pairing is
    # what nobody can explain away without going and looking, so the pairing is what gets
    # reported, worded as the coincidence it is.
    upstream = tmp_path / "upstream"
    subprocess.run(["git", "clone", "-q", str(repo), str(upstream)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(upstream)], cwd=str(repo), check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    commit(pinned.path, "leaked")
    commit(upstream, "somebody-else")
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "1 commit(s)" in caveats[0] and "cannot be ruled out" in caveats[0]
    project_mod.release(pinned)


def test_a_moving_remote_alone_is_somebody_elses_work(repo: Path, tmp_path: Path) -> None:
    # Said out loud because it is the false positive that would have made this useless:
    # in a checkout several sessions push from, origin/main moves during every round.
    upstream = tmp_path / "upstream"
    subprocess.run(["git", "clone", "-q", str(repo), str(upstream)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(upstream)], cwd=str(repo), check=True)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    pinned = project_mod.pin(repo, work=tmp_path / "work")
    commit(upstream, "somebody-else")
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=str(repo), check=True)

    assert project_mod.escaped(pinned) == ()
    project_mod.release(pinned)


def test_an_unpinned_run_is_not_asked(repo: Path, tmp_path: Path) -> None:
    # Nothing was fenced off, so there is nothing to have escaped from; a caveat here
    # would be describing the operator's own tree back at them.
    unpinned = project_mod.pin(repo, work=tmp_path / "work", enabled=False)
    assert project_mod.escaped(unpinned) == ()
    assert project_mod.escaped(None) == ()
