"""Tests for the capture guard: a refresh must never lose a pinned commit.

`git bundle create --all` packs *refs*. A story's pin stops being reachable as soon as the
source repo's branches move off it, and the capture that follows then overwrites a working
bundle with one that cannot check the story out — a loss whose only symptom arrives much
later, in a replay, with the artifact that had the commit already gone.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "replay", Path(__file__).parents[1] / "replay.py"
)
# A spec and a loader are what a real file on disk always yields; the import machinery
# answers None for the cases this is not (a namespace package, an unimportable path).
assert _spec is not None and _spec.loader is not None
replay = importlib.util.module_from_spec(_spec)
sys.modules["replay"] = replay
_spec.loader.exec_module(replay)


def run(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    run("add", name, cwd=repo)
    run("-c", "user.email=t@example.com", "-c", "user.name=T", "commit", "-qm", name, cwd=repo)
    return run("rev-parse", "HEAD", cwd=repo)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    repo = tmp_path / "app"
    repo.mkdir()
    run("init", "-q", "-b", "main", cwd=repo)
    return repo


def bundle_of(source: Path, tmp_path: Path) -> Path:
    path = tmp_path / "frozen.bundle"
    run("bundle", "create", str(path), "--all", cwd=source)
    return path


def test_a_pin_on_the_branch_tip_is_bundled(source: Path, tmp_path: Path) -> None:
    first = commit(source, "one")
    commit(source, "two")
    fixture = replay.Fixture(
        name="frozen", source=source, app=None, stories=[{"story": "s", "qa": first}]
    )
    assert replay.unbundled_commits(fixture, bundle_of(source, tmp_path)) == []


def test_a_pin_no_ref_reaches_is_reported_not_silently_dropped(
    source: Path, tmp_path: Path
) -> None:
    """The real failure: the lane that finished the story was abandoned, not merged.

    The commit is still in the source's object store — `cat-file` finds it, so does a
    reflog-aware read — which is exactly why nothing about the capture complains.
    """
    base = commit(source, "base")
    orphan = commit(source, "orphan")
    run("reset", "-q", "--hard", base, cwd=source)
    fixture = replay.Fixture(
        name="frozen",
        source=source,
        app=None,
        stories=[{"story": "expense-list", "qa": orphan, "docs": base}],
    )
    assert replay.unbundled_commits(fixture, bundle_of(source, tmp_path)) == [
        ("expense-list", "qa", orphan)
    ]


def test_a_pin_reachable_only_from_a_second_branch_still_counts(
    source: Path, tmp_path: Path
) -> None:
    """Reachability, not ancestry of HEAD — `--all` packs every ref, so the guard must too."""
    base = commit(source, "base")
    side = commit(source, "side")
    run("branch", "keep", side, cwd=source)
    run("reset", "-q", "--hard", base, cwd=source)
    fixture = replay.Fixture(
        name="frozen", source=source, app=None, stories=[{"story": "s", "qa": side}]
    )
    assert replay.unbundled_commits(fixture, bundle_of(source, tmp_path)) == []
