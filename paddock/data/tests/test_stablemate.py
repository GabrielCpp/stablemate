"""Tests for `_stablemate` — the process boundary a paddock task drives stablemate across.

The property most of these protect is one: a pinned round runs the pinned tree's
code and reads the pinned tree's paths. It broke once invisibly — `uv run --project`
against the workspace anchor installs none of the tools, so the command fell back to
`$PATH`, where an editable install resolved every workflow module to the operator's live
tree, straight through the pin. Nothing failed; the round just measured the wrong code.
"""

from __future__ import annotations

import contextlib
import importlib.util
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from paddock import project as project_mod
from paddock.registry import REGISTRY

DATA = Path(__file__).parents[1]


@contextlib.contextmanager
def _tasks_dir_on_path() -> Iterator[None]:
    """Stand in for the interpreter, exactly as `paddock.loader` does when it loads a task."""
    saved = sys.path[:]
    sys.path.insert(0, str(DATA / "tasks"))
    try:
        yield
    finally:
        sys.path[:] = saved


def _load(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None  # noqa: S101 - a real file on disk
    module = importlib.util.module_from_spec(spec)
    REGISTRY.reset()
    with _tasks_dir_on_path():
        sys.modules[name] = module
        spec.loader.exec_module(module)
    REGISTRY.reset()
    return module


sm = _load("_stablemate", DATA / "tasks" / "_stablemate.py")


def test_uv_run_names_the_member_environment() -> None:
    """The prefix must carry `--package`, or the tool comes off `$PATH` — the live tree."""
    assert sm.uv_run(Path("/x/checkout"), "workhorse-workflows") == [
        "uv", "run", "--project", "/x/checkout", "--package", "workhorse-workflows",
    ]


def test_pin_config_writes_the_pinned_checkout_as_stablemate_dir(
    tmp_path: Path, monkeypatch  # noqa: ANN001 - pytest fixture
) -> None:
    """A pinned run's effective config points at the worktree, never the live tree.

    `stablemate_dir` names "the checkout", and everything a trial derives from it
    (base-library discovery, farrier's launcher) must read the tree the round is
    measured on — copying the machine's value verbatim hands every trial the operator's
    live tree through the config, past the pin.
    """
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
    run = SimpleNamespace(scratch=scratch, config=tracked, project=worktree)

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


# `no_leaks` — did the round write into the toolchain it was being measured on.
#
# The question it asks changed when the pin gained its fence. A round can no longer commit
# into the toolchain — the pinned tree is not a repository — so a check keyed on `git log`
# would now be a check that can never fire, which is worse than no check at all: it reports
# clean forever and nobody notices it stopped looking. What replaced it is also stricter.
# A round that patched the toolchain and never committed spent every remaining hour running
# the patch, so its scorecard is not a measurement of the sha in its ledger — and the
# commit-keyed version called that clean.


def test_a_quiet_round_leaks_nothing(toolchain: Path) -> None:
    with sm.no_leaks(toolchain, pinned=True):
        pass


def test_a_round_that_patched_the_toolchain_voids_its_own_numbers(toolchain: Path) -> None:
    with pytest.raises(sm.TrialError, match="instead of its sandboxes"):  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=True):
            (toolchain / "README.md").write_text("patched mid-round\n", encoding="utf-8")


def test_a_new_file_in_the_toolchain_is_a_leak_too(toolchain: Path) -> None:
    """Untracked, because that is how a leaked *addition* shows up and a check watching only
    modifications would miss a whole new module dropped into the tree."""
    with pytest.raises(sm.TrialError, match="instead of its sandboxes"):  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=True):
            (toolchain / "sneaked.py").write_text("x = 1\n", encoding="utf-8")


def test_what_was_already_dirty_is_not_this_rounds_doing(toolchain: Path) -> None:
    """Said out loud because it decides the shape: the comparison is a set difference, not a
    "is it clean", so a pin taken from a dirty source does not accuse the round of an edit
    that was there before it started."""
    (toolchain / "README.md").write_text("already edited\n", encoding="utf-8")
    with sm.no_leaks(toolchain, pinned=True):
        pass


def test_a_round_that_committed_its_patch_cannot_hide_behind_a_clean_tree(
    toolchain: Path,
) -> None:
    """The evasion `status`-only leak detection has: patch, commit, and the tree is clean.

    The pin is fenced, but the git directory paddock stashed beside it is one `ls ..` from
    the sandbox — so the commit is available to a round that goes looking, and this is the
    trial-level half of noticing it. Round-level `escaped` says the round did it; this
    says which trial.
    """
    stash = project_mod.stashed_git_dir(toolchain)
    where = ["--git-dir", str(stash), "--work-tree", str(toolchain)]
    with pytest.raises(sm.TrialError, match="instead of its sandboxes"):  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=True):
            (toolchain / "patched.py").write_text("x = 1\n", encoding="utf-8")
            for args in (["add", "-A"], ["commit", "-q", "-m", "patched"]):
                subprocess.run(["git", *where, *args], cwd=str(toolchain), check=True)  # noqa: S603, S607 - git, fixed args
            assert not sm.git(*where, "status", "--porcelain", cwd=toolchain).strip()  # noqa: S101 - the premise


def test_an_unpinned_round_reports_the_change_without_naming_a_culprit(toolchain: Path) -> None:
    """The same evidence, the weaker claim — because `--no-pin-project` and a pin that could
    not be made both leave the round driving a checkout other people commit to.

    A teammate landing a commit mid-round produced exactly this once, and the report accused
    the round of it; somebody then spent their afternoon disproving a finding the check never
    had the standing to make. The round still stops — unpinned is the one case where this is
    the only tripwire there is — but what it stops on is "the tree moved", not "you moved it".
    """
    with pytest.raises(sm.TrialError, match="not knowable from here") as raised:  # noqa: PT012 - the cm is the subject
        with sm.no_leaks(toolchain, pinned=False):
            (toolchain / "README.md").write_text("somebody else's commit\n", encoding="utf-8")

    assert "instead of its sandboxes" not in str(raised.value)  # noqa: S101 - the accusation is the defect


def test_only_a_pin_that_was_actually_made_counts_as_held(tmp_path: Path) -> None:
    """`pin_held` is what the callers pass, so its three cases are the check's three cases.

    A degraded pin reports `Project(pinned=False)` rather than `None`, which is the case that
    made this necessary: the run was configured for a pin, the ledger records the attempt, and
    the tree under it is still shared.
    """

    def pin(*, pinned: bool) -> project_mod.Project:
        return project_mod.Project(
            path=tmp_path, source=tmp_path, head="a" * 40, pinned=pinned, dirty=False
        )

    assert sm.pin_held(pin(pinned=True))  # noqa: S101 - the point of the test
    assert not sm.pin_held(pin(pinned=False))  # noqa: S101 - the degraded pin this exists for
    assert not sm.pin_held(None)  # noqa: S101 - a task driving no project at all
