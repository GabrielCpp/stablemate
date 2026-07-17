"""The shared base-library cache: fetch-once, freeze, never shadow a real checkout.

Standalone + pytest-compatible. No network: the clone is patched at its seam and
faked by building the expected layout on disk.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from stablemate_core import base_cache as bc


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    """Never touch the real ~/.cache/stablemate from a test."""
    monkeypatch.setenv(bc.CACHE_DIR_ENV, str(tmp_path / "cache"))
    monkeypatch.delenv(bc.FETCH_ENV, raising=False)


def _fake_clone(dest: Path, *, commit: str = "abc123") -> bool:
    """Build what a real clone would leave behind."""
    lib = dest / bc.BASE_SUBPATH
    (lib / "workflows").mkdir(parents=True)
    (dest / ".git").mkdir(parents=True)
    (dest / ".git" / "COMMIT").write_text(commit)
    return True


# --- fetch -------------------------------------------------------------------


def test_fetches_when_absent_and_returns_the_library(monkeypatch, capsys):
    monkeypatch.setattr(bc, "_clone_into", lambda dest: _fake_clone(dest))
    monkeypatch.setattr(bc, "cached_commit", lambda clone=None: "abc123")

    base = bc.ensure_cached_base()

    assert base is not None and base.is_dir()
    assert base == bc.cached_library_dir() / bc.BASE_SUBPATH
    # A fetch writes ~11M and hits the network; it must announce itself.
    assert "fetching base library" in capsys.readouterr().out


def test_second_call_does_not_refetch(monkeypatch):
    """Fetch-once-then-freeze: the property that stops a week-long run mutating."""
    calls = []

    def clone(dest):
        calls.append(dest)
        return _fake_clone(dest)

    monkeypatch.setattr(bc, "_clone_into", clone)
    monkeypatch.setattr(bc, "cached_commit", lambda clone=None: "abc123")

    bc.ensure_cached_base()
    bc.ensure_cached_base()
    bc.ensure_cached_base()

    assert len(calls) == 1


def test_deleting_the_cache_is_the_upgrade_path(monkeypatch):
    commits = iter(["old111", "new222"])
    monkeypatch.setattr(
        bc, "_clone_into", lambda dest: _fake_clone(dest, commit=next(commits))
    )
    monkeypatch.setattr(bc, "cached_commit", lambda clone=None: "x")

    bc.ensure_cached_base()
    first = (bc.cached_library_dir() / ".git" / "COMMIT").read_text()

    import shutil

    shutil.rmtree(bc.cached_library_dir())
    bc.ensure_cached_base()
    second = (bc.cached_library_dir() / ".git" / "COMMIT").read_text()

    assert (first, second) == ("old111", "new222")


# --- fail-soft ---------------------------------------------------------------


def test_failed_clone_returns_none_and_leaves_no_debris(monkeypatch):
    """Offline must degrade to "not found here", exactly as before this layer."""
    monkeypatch.setattr(bc, "_clone_into", lambda dest: False)

    assert bc.ensure_cached_base() is None
    leftovers = list(bc.cache_root().glob(".library-fetch-*"))
    assert leftovers == []


def test_fetch_can_be_disabled(monkeypatch):
    monkeypatch.setenv(bc.FETCH_ENV, "0")
    monkeypatch.setattr(
        bc, "_clone_into", lambda dest: pytest.fail("must not fetch when disabled")
    )
    assert bc.ensure_cached_base() is None


@pytest.mark.parametrize("value,expected", [("0", False), ("false", False),
                                            ("no", False), ("off", False),
                                            ("1", True), ("yes", True)])
def test_fetch_allowed_parsing(monkeypatch, value, expected):
    monkeypatch.setenv(bc.FETCH_ENV, value)
    assert bc.fetch_allowed() is expected


def test_missing_git_binary_is_not_a_crash(monkeypatch):
    def boom(*a, **k):
        raise OSError("No such file or directory: 'git'")

    monkeypatch.setattr(bc.subprocess, "run", boom)
    assert bc._clone_into(bc.cache_root() / "tmp") is False


def test_clone_timeout_is_not_a_crash(monkeypatch):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="git", timeout=1)

    monkeypatch.setattr(bc.subprocess, "run", boom)
    assert bc._clone_into(bc.cache_root() / "tmp") is False


def test_wrong_layout_after_fetch_is_reported_not_returned(monkeypatch):
    """If the library moves inside the repo, say so rather than return a bad path."""

    def clone_without_library(dest):
        (dest / ".git").mkdir(parents=True)
        return True

    monkeypatch.setattr(bc, "_clone_into", clone_without_library)
    assert bc.ensure_cached_base() is None


def test_concurrent_fetch_loser_discards_its_clone(monkeypatch):
    """Two runs race; the rename settles it with no lock file to leak."""
    monkeypatch.setattr(bc, "_clone_into", lambda dest: _fake_clone(dest))
    monkeypatch.setattr(bc, "cached_commit", lambda clone=None: "abc123")

    # The other run lands its clone in the gap between our clone and our rename, so
    # ours hits a non-empty target -- the exact race the rename is there to settle.
    def rename_conflict(self, target):
        _fake_clone(Path(target), commit="theirs")
        raise OSError("Directory not empty")

    monkeypatch.setattr(Path, "rename", rename_conflict)

    base = bc.ensure_cached_base()

    assert base is not None and base.is_dir()
    assert (bc.cached_library_dir() / ".git" / "COMMIT").read_text() == "theirs"
    assert list(bc.cache_root().glob(".library-fetch-*")) == []


# --- lookup is not a fetch ---------------------------------------------------


def test_cached_base_never_fetches(monkeypatch):
    """A lookup that downloads 16M is a trap — `config show` would trigger it.

    This split is why test_library_layers' resolution-order test can assert None
    without touching the network.
    """
    monkeypatch.setattr(
        bc, "_clone_into", lambda dest: pytest.fail("lookup must never fetch")
    )
    assert bc.cached_base() is None


def test_cached_base_finds_an_existing_clone(monkeypatch):
    _fake_clone(bc.cached_library_dir())
    monkeypatch.setattr(
        bc, "_clone_into", lambda dest: pytest.fail("must not fetch when present")
    )
    assert bc.cached_base() == bc.cached_library_dir() / bc.BASE_SUBPATH


def test_base_library_dir_does_not_fetch(monkeypatch):
    """The regression that started this: base_library_dir cloned into the real
    ~/.cache during a unit test run."""
    from stablemate_core.discovery import base_library_dir

    monkeypatch.setattr(
        bc, "_clone_into", lambda dest: pytest.fail("resolution must never fetch")
    )
    monkeypatch.delenv("STABLEMATE_BASE_DIR", raising=False)
    base_library_dir()


# --- provenance --------------------------------------------------------------


def test_cached_commit_none_when_absent():
    assert bc.cached_commit() is None


def test_cached_commit_reads_head(monkeypatch, tmp_path):
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)

    class Proc:
        stdout = "deadbeef\n"

    monkeypatch.setattr(bc.subprocess, "run", lambda *a, **k: Proc())
    assert bc.cached_commit(clone) == "deadbeef"


def test_cache_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv(bc.CACHE_DIR_ENV, str(tmp_path / "elsewhere"))
    assert bc.cache_root() == tmp_path / "elsewhere"


def test_clone_url_is_anonymous():
    """A machine running this has no deploy key and no business having one."""
    assert bc.BASE_REPO_URL.startswith("https://")
    assert not bc.BASE_REPO_URL.startswith("git@")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
