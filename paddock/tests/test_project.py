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
    # Through the stashed git dir: the pin itself is fenced off from git on purpose.
    assert project_mod.read(pinned, "rev-parse", "HEAD").stdout.strip() == pinned.head
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
    subprocess.run(
        ["git", "remote", "add", "origin", "https://example.com/acme.git"],
        cwd=str(repo), check=True,
    )

    pinned = project_mod.pin(repo, work=tmp_path / "work")

    assert pinned is not None and pinned.pinned
    assert project_mod.read(pinned, "remote").stdout.split() == []
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


def test_the_toolchain_is_not_a_repository_the_round_can_commit_into(
    repo: Path, tmp_path: Path
) -> None:
    """The fence, from the round's side: git in the pin fails, and says why.

    A gitfile pointing nowhere rather than a deleted `.git`, because the deleted version
    lets git walk *up* — and a `git commit` in a work directory that happens to sit under
    some other repository would quietly land there instead.
    """
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    outer = subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "leak"],
        cwd=str(pinned.path), capture_output=True, text=True, check=False,
    )
    assert outer.returncode != 0
    assert project_mod.FENCE in outer.stderr
    project_mod.release(pinned)


def test_editing_the_toolchain_mid_round_is_a_self_touch(repo: Path, tmp_path: Path) -> None:
    # The one people underrate, because the tree gets deleted and looks harmless: the
    # round spent the rest of its hours running the edited code, so whatever the scorecard
    # says, it is not a measurement of the sha in the ledger.
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None
    (pinned.path / "README.md").write_text("patched mid-round\n", encoding="utf-8")

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "1 file(s)" in caveats[0] and "not the sha in this ledger" in caveats[0]
    project_mod.release(pinned)


def test_a_round_that_rebuilds_the_repository_says_so(repo: Path, tmp_path: Path) -> None:
    # The fence is a barrier, not a proof. `git init` gets past it — and is exactly the
    # thing nobody does by accident, so getting past it is itself the finding.
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


def test_a_pin_that_was_asked_for_and_not_made_is_a_caveat(repo: Path, tmp_path: Path) -> None:
    """The promise, not the escape. A degraded pin has to reach the result, not the log.

    This is the shape that hid a live bug for weeks: `_project` handed `pin()` a path one
    level short of the repo root, every clone failed, every round ran unpinned, and the
    only announcement was a WARNING nobody greps for.
    """
    # `pin()` degrades on a source that is not a repository, which is the same end state
    # the resolution bug produced.
    not_a_repo = tmp_path / "not-a-repo"
    not_a_repo.mkdir()
    degraded = project_mod.pin(not_a_repo, work=tmp_path / "work")
    assert degraded is not None and not degraded.pinned

    caveats = project_mod.degraded(degraded, requested=True)
    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.UNPINNED)
    assert str(not_a_repo) in caveats[0]


def test_a_deliberate_opt_out_is_not_caveated(repo: Path, tmp_path: Path) -> None:
    """`--no-pin-project` is a decision, and `pinned: false` in the ledger keeps it
    answerable. Marking it too would put the caveat on rounds nobody was misled about,
    which is how a disqualification channel gets read as noise."""
    off = project_mod.pin(repo, work=tmp_path / "work", enabled=False)
    assert project_mod.degraded(off, requested=False) == ()
    # And a task that drives no project never had a pin to keep.
    assert project_mod.degraded(None, requested=True) == ()


def test_a_pin_that_was_made_says_nothing(repo: Path, tmp_path: Path) -> None:
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None and pinned.pinned
    assert project_mod.degraded(pinned, requested=True) == ()


def test_an_unpinned_run_is_not_asked(repo: Path, tmp_path: Path) -> None:
    # Nothing was fenced off, so there is nothing to have escaped from; a caveat here
    # would be describing the operator's own tree back at them.
    unpinned = project_mod.pin(repo, work=tmp_path / "work", enabled=False)
    assert project_mod.escaped(unpinned) == ()
    assert project_mod.escaped(None) == ()


# The stash the fence creates is itself a route, and these four are what notices it.
#
# `.git` is renamed aside rather than deleted so the round can still be *asked* about
# afterwards, and where it goes is one directory up from the round's own sandbox. That
# makes it a whole repository to anyone who runs `ls ..` — and a round that commits
# through it leaves the fence byte-identical and, once committed, leaves the tree clean.
# Every check keyed on the fence or on `status` reads that round as untouched. So the
# three arms below ask the stash instead, and the fourth covers the move that would
# otherwise switch all of them off at once.


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

    # The point of the test: after the commit the fence stands and the tree is clean, so
    # the two older arms both say nothing.
    assert (pinned.path / ".git").read_text(encoding="utf-8") == project_mod.FENCE_GITFILE
    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "moved the pin's HEAD" in caveats[0]
    project_mod.release(pinned)


def test_a_round_that_unwinds_its_own_commit_still_says_so(repo: Path, tmp_path: Path) -> None:
    """The restore-to-innocence shape: patch, run the patched toolchain for an hour, then
    `reset --hard` back to the pinned sha so HEAD, the refs and the tree all match again.

    A HEAD comparison alone cannot see it. The objects can — nothing else in a pin nobody
    fetches into makes a commit the pinned sha does not reach, and `--reflog` is what
    keeps them reachable across the reset.
    """
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
    # Every ref, not a prefix: a branch, a tag and a note all answer the same question,
    # and naming prefixes is how one of them gets forgotten.
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
    # The move that would otherwise turn every arm above off at once: with nothing to read
    # through, each git call fails, each answer comes back empty, and a round that deleted
    # the evidence would seal as the quietest one of the day.
    pinned = project_mod.pin(repo, work=tmp_path / "work")
    assert pinned is not None and pinned.git_dir is not None
    shutil.rmtree(pinned.git_dir)

    caveats = project_mod.escaped(pinned)

    assert len(caveats) == 1
    assert caveats[0].startswith(project_mod.SELF_TOUCHED)
    assert "nothing here can say what the round did" in caveats[0]
    project_mod.release(pinned)
