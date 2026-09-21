"""Machine scratch lands in the cache, and two checkouts never share one."""
from __future__ import annotations

from pathlib import Path

import pytest
from workhorse.scratch import scratch_dir


def test_scratch_lands_under_the_configured_cache_and_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller gets a directory it can write to immediately."""
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))

    got = scratch_dir("okf-walkthrough", tmp_path / "repo")

    assert got.is_dir()
    assert got.is_relative_to(tmp_path / "cache")
    assert "okf-walkthrough" in got.parts


def test_two_checkouts_with_the_same_name_get_different_scratch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree and its origin share a basename and must not share a browser profile."""
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    one = tmp_path / "a" / "web-app"
    two = tmp_path / "b" / "web-app"
    one.mkdir(parents=True)
    two.mkdir(parents=True)

    assert scratch_dir("okf-walkthrough", one) != scratch_dir("okf-walkthrough", two)
    assert scratch_dir("okf-walkthrough", one).name.startswith("web-app-")


def test_the_same_checkout_is_stable_across_spellings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resumed run reaches its own profile, however the path was spelled."""
    monkeypatch.setenv("STABLEMATE_CACHE_DIR", str(tmp_path / "cache"))
    repo = tmp_path / "repo"
    repo.mkdir()

    assert scratch_dir("x", repo) == scratch_dir("x", tmp_path / "sub" / ".." / "repo")
