"""``write_private`` — the 0600-before-content write every secret-bearing file uses."""

from __future__ import annotations

import stat
from pathlib import Path

from saddlebag.workhorse import write_private


def test_written_file_carries_the_text(tmp_path: Path):
    path = write_private(tmp_path / ".workhorse" / "run.env", "KEY=value\n")
    assert path.read_text(encoding="utf-8") == "KEY=value\n"


def test_written_file_is_owner_only(tmp_path: Path):
    """A file that may hold a secret must never be group- or world-readable."""
    path = write_private(tmp_path / "run.env", "KEY=value\n")
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"expected 0600, got {mode:04o}"


def test_parent_directories_are_created(tmp_path: Path):
    path = write_private(tmp_path / "deep" / "nested" / "run.env", "KEY=value\n")
    assert path.exists()


def test_overwriting_tightens_the_mode_and_drops_old_content(tmp_path: Path):
    path = tmp_path / "run.env"
    path.write_text("stale, world-readable garbage", encoding="utf-8")
    path.chmod(0o644)

    write_private(path, "KEY=value\n")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text(encoding="utf-8") == "KEY=value\n"
