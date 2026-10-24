"""Tests for `paddock.tasks.stablemate`, the process boundary a paddock task drives stablemate across."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from paddock import project as project_mod
from paddock.runner import Run
from paddock.tasks import stablemate as sm


def test_uv_run_names_the_member_environment() -> None:
    """The prefix must carry `--package`, or the tool comes off `$PATH` — the live tree."""
    assert sm.uv_run(Path("/x/checkout"), "workhorse-workflows") == [
        "uv", "run", "--project", "/x/checkout", "--package", "workhorse-workflows",
    ]


def test_pin_config_writes_the_pinned_checkout_as_stablemate_dir(
    tmp_path: Path, monkeypatch  # noqa: ANN001 - pytest fixture
) -> None:
    """A pinned run's effective config points at the worktree, never the live tree."""
    worktree = tmp_path / "project"
    worktree.mkdir()
    (worktree / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tracked = tmp_path / "models.toml"
    tracked.write_text("# model tables\n", encoding="utf-8")
    monkeypatch.setattr(
        sm.core_config,
        "load_config",
        lambda: {"library_dir": "/lib", "stablemate_dir": "/live/tree"},
    )
    run = cast(Run, SimpleNamespace(scratch=scratch, config=tracked, project=worktree))

    sm.pin_config(run)

    text = sm.effective(run).read_text(encoding="utf-8")
    assert f'stablemate_dir = "{worktree}"' in text
    assert "/live/tree" not in text
    assert 'library_dir = "/lib"' in text


@pytest.fixture
def toolchain(tmp_path: Path) -> Path:
    """A stand-in checkout, pinned and fenced the way a round receives one."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "README.md").write_text("acme\n", encoding="utf-8")
    for args in (
        ["init", "-q", "--initial-branch", "main"],
        ["config", "user.email", "benchmark@example.com"],
        ["config", "user.name", "stablemate benchmark"],
        ["add", "-A"],
        ["commit", "-q", "-m", "first"],
    ):
        subprocess.run(["git", *args], cwd=str(source), check=True)  # noqa: S603, S607 - git, fixed args
    pinned = project_mod.pin(source, work=tmp_path / "work")
    assert pinned is not None and pinned.pinned  # noqa: S101 - the fixture's own precondition
    return pinned.path




def test_a_quiet_round_leaks_nothing(toolchain: Path) -> None:
    with sm.no_leaks(toolchain, pinned=True):
        pass


def test_a_round_that_patched_the_toolchain_voids_its_own_numbers(toolchain: Path) -> None:
    with pytest.raises(sm.TrialError, match="instead of its sandboxes"):  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=True):
            (toolchain / "README.md").write_text("patched mid-round\n", encoding="utf-8")


def test_a_new_file_in_the_toolchain_is_a_leak_too(toolchain: Path) -> None:
    """Untracked, because that is how a leaked *addition* shows up and a check watching only modifications would miss a whole new module dropped into the tree."""
    with pytest.raises(sm.TrialError, match="instead of its sandboxes"):  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=True):
            (toolchain / "sneaked.py").write_text("x = 1\n", encoding="utf-8")


def test_what_was_already_dirty_is_not_this_rounds_doing(toolchain: Path) -> None:
    """Said out loud because it decides the shape: the comparison is a set difference, not a "is it clean", so a pin taken from a dirty source does not accuse the round of an edit that was there before it started."""
    (toolchain / "README.md").write_text("already edited\n", encoding="utf-8")
    with sm.no_leaks(toolchain, pinned=True):
        pass


def test_a_round_that_committed_its_patch_cannot_hide_behind_a_clean_tree(
    toolchain: Path,
) -> None:
    """The evasion `status`-only leak detection has: patch, commit, and the tree is clean."""
    stash = project_mod.stashed_git_dir(toolchain)
    where = ["--git-dir", str(stash), "--work-tree", str(toolchain)]
    with pytest.raises(sm.TrialError, match="instead of its sandboxes"):  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=True):
            (toolchain / "patched.py").write_text("x = 1\n", encoding="utf-8")
            for args in (["add", "-A"], ["commit", "-q", "-m", "patched"]):
                subprocess.run(["git", *where, *args], cwd=str(toolchain), check=True)  # noqa: S603, S607 - git, fixed args
            assert not sm.git(*where, "status", "--porcelain", cwd=toolchain).strip()  # noqa: S101 - the premise


def test_an_unpinned_round_reports_the_change_without_naming_a_culprit(toolchain: Path) -> None:
    """The same evidence, the weaker claim — because `--no-pin-project` and a pin that could not be made both leave the round driving a checkout other people commit to."""
    with pytest.raises(sm.TrialError, match="not knowable from here") as raised:  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=False):
            (toolchain / "README.md").write_text("somebody else's commit\n", encoding="utf-8")

    assert "instead of its sandboxes" not in str(raised.value)  # noqa: S101 - the accusation is the defect


def test_only_a_pin_that_was_actually_made_counts_as_held(tmp_path: Path) -> None:
    """`pin_held` is what the callers pass, so its three cases are the check's three cases."""

    def pin(*, pinned: bool) -> project_mod.Project:
        return project_mod.Project(
            path=tmp_path, source=tmp_path, head="a" * 40, pinned=pinned, dirty=False
        )

    assert sm.pin_held(pin(pinned=True))  # noqa: S101 - the point of the test
    assert not sm.pin_held(pin(pinned=False))  # noqa: S101 - the degraded pin this exists for
    assert not sm.pin_held(None)  # noqa: S101 - a task driving no project at all


def test_install_agents_runs_farrier_install_on_the_stage(tmp_path: Path) -> None:
    seen: list[tuple[str, ...]] = []

    def cli(*argv: str, **kwargs: object) -> object:
        seen.append(argv)
        assert kwargs["check"] is True
        return object()

    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    stage = tmp_path / "stage"
    run = cast(Run, SimpleNamespace(cli=cli, project=checkout, stage=stage))

    sm.install_agents(run)

    assert seen == [(
        "uv", "run", "--project", str(checkout), "--package", "farrier",
        "farrier", "install", "--repo", str(stage),
    )]
