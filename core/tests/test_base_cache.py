"""The shared base-library cache: fetch-once, freeze, never shadow a real checkout.

Standalone + pytest-compatible. No network: the fetch is patched at its seam and faked
by building the expected layout on disk — `base-library/library/` plus the `.commit`
sidecar, which is what a sparse fetch leaves behind now that `.git` does not survive it.
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
    """Build what a real fetch would leave behind: documents and a commit sidecar."""
    lib = dest / bc.BASE_SUBPATH
    (lib / "library").mkdir(parents=True)
    (dest / bc.COMMIT_FILE).write_text(f"{commit}\n")
    return True


# --- fetch -------------------------------------------------------------------


def test_fetches_when_absent_and_returns_the_library(monkeypatch, capsys):
    monkeypatch.setattr(bc, "_clone_into", lambda dest: _fake_clone(dest))
    monkeypatch.setattr(bc, "cached_commit", lambda clone=None: "abc123")

    base = bc.ensure_cached_base()

    assert base is not None and base.is_dir()
    assert base == bc.cached_library_dir() / bc.BASE_SUBPATH
    # A fetch hits the network and writes to the cache; it must announce itself, and
    # say how much it is taking — the narrowing is the operator-visible part.
    out = capsys.readouterr().out
    assert "fetching base library" in out
    assert f"{bc.BASE_SUBPATH}/ only" in out


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
    bc.ensure_cached_base()
    first = bc.cached_commit()

    import shutil

    shutil.rmtree(bc.cached_library_dir())
    bc.ensure_cached_base()
    second = bc.cached_commit()

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
        dest.mkdir(parents=True)
        (dest / bc.COMMIT_FILE).write_text("abc123\n")
        return True

    monkeypatch.setattr(bc, "_clone_into", clone_without_library)
    assert bc.ensure_cached_base() is None


def test_concurrent_fetch_loser_discards_its_clone(monkeypatch):
    """Two runs race; the rename settles it with no lock file to leak."""
    monkeypatch.setattr(bc, "_clone_into", lambda dest: _fake_clone(dest))

    # The other run lands its clone in the gap between our clone and our rename, so
    # ours hits a non-empty target -- the exact race the rename is there to settle.
    def rename_conflict(self, target):
        _fake_clone(Path(target), commit="theirs")
        raise OSError("Directory not empty")

    monkeypatch.setattr(Path, "rename", rename_conflict)

    base = bc.ensure_cached_base()

    assert base is not None and base.is_dir()
    assert bc.cached_commit() == "theirs"
    assert list(bc.cache_root().glob(".library-fetch-*")) == []


# --- lookup is not a fetch ---------------------------------------------------


def test_cached_base_never_fetches(monkeypatch):
    """A lookup that reaches the network is a trap — `config show` would trigger it.

    This split is why a resolution-order test can assert None without touching the
    network.
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


def test_cached_commit_reads_the_sidecar_not_git(monkeypatch, tmp_path):
    """No `git` subprocess is involved: the cache is documents, `.git` is gone."""
    clone = tmp_path / "clone"
    clone.mkdir(parents=True)
    (clone / bc.COMMIT_FILE).write_text("deadbeef\n")

    monkeypatch.setattr(
        bc.subprocess, "run", lambda *a, **k: pytest.fail("must not shell out to git")
    )
    assert bc.cached_commit(clone) == "deadbeef"


def test_cached_commit_ignores_a_leftover_git_dir(tmp_path):
    """A hand-assembled or pre-narrowing cache with `.git` but no sidecar reads as
    unknown rather than as a lie — `?` in the operator's log, not a stale sha."""
    clone = tmp_path / "clone"
    (clone / ".git").mkdir(parents=True)
    assert bc.cached_commit(clone) is None


def test_cache_dir_override(monkeypatch, tmp_path):
    monkeypatch.setenv(bc.CACHE_DIR_ENV, str(tmp_path / "elsewhere"))
    assert bc.cache_root() == tmp_path / "elsewhere"


def test_clone_url_is_anonymous():
    """A machine running this has no deploy key and no business having one."""
    assert bc.BASE_REPO_URL.startswith("https://")
    assert not bc.BASE_REPO_URL.startswith("git@")


# --- the narrowing ------------------------------------------------------------


def test_the_fetch_is_sparse_and_leaves_no_repository(monkeypatch, tmp_path):
    """The trust posture, asserted at the seam: sparse `base-library/`, then documents.

    A regression here would be silent — a full clone works perfectly well and simply
    puts every `.py` in this repo inside the operator's cache, which is the thing the
    narrowing exists to prevent.
    """
    calls: list[list[str]] = []
    dest = tmp_path / "fetched"

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if cmd[:2] == ["git", "clone"]:
            (dest / ".git").mkdir(parents=True)
            (dest / bc.BASE_SUBPATH / "library").mkdir(parents=True)
        return subprocess.CompletedProcess(cmd, 0, stdout="deadbeef\n", stderr="")

    monkeypatch.setattr(bc.subprocess, "run", fake_run)
    assert bc._clone_into(dest) is True

    clone = next(c for c in calls if c[:2] == ["git", "clone"])
    assert "--sparse" in clone and "--filter=blob:none" in clone
    # `--no-cone`: cone mode would also check out the repository root.
    assert calls[1][3:] == [
        "sparse-checkout",
        "set",
        "--no-cone",
        f"/{bc.BASE_SUBPATH}/",
    ]

    assert not (dest / ".git").exists(), "the cache must hold documents, not a repo"
    assert (dest / bc.COMMIT_FILE).read_text().strip() == "deadbeef"


def test_a_failed_sparse_checkout_does_not_fall_back_to_a_full_clone(
    monkeypatch, tmp_path
):
    """Fail closed. A git too old for `sparse-checkout` must get no library at all,
    rather than a full clone that quietly drops the posture."""
    dest = tmp_path / "fetched"

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "clone"]:
            (dest / ".git").mkdir(parents=True)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            cmd, 1, stdout="", stderr="git: 'sparse-checkout' is not a git command"
        )

    monkeypatch.setattr(bc.subprocess, "run", fake_run)
    assert bc._clone_into(dest) is False


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
