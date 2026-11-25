"""No tracked file names a retired harness outside the changelogs and the book decisions."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from stablemate_core.harness import RETIRED

DEFINITION = "core/stablemate_core/harness.py"


def _pattern(names: frozenset[str]) -> re.Pattern[str]:
    return re.compile(r"\b(?:" + "|".join(sorted(re.escape(name) for name in names)) + r")\b", re.IGNORECASE)


def _excluded(path: str) -> bool:
    parts = Path(path).parts
    return path == DEFINITION or parts[-1] == "CHANGELOG.md" or "decisions" in parts[:-1]


def _root() -> Path:
    if shutil.which("git") is None:
        pytest.skip("git is absent")
    done = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        pytest.skip("not inside a git checkout")
    return Path(done.stdout.strip())


def _hits(root: Path, names: frozenset[str], paths: list[str]) -> list[str]:
    pattern = _pattern(names)
    found: list[str] = []
    for path in paths:
        file = root / path
        if _excluded(path) or file.is_symlink() or not file.is_file():
            continue
        try:
            text = file.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                found.append(f"{path}:{number}")
    return found


def test_no_tracked_file_names_a_retired_harness() -> None:
    root = _root()
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, check=True
    ).stdout
    hits = _hits(root, RETIRED, [path for path in listed.split("\0") if path])
    assert not hits, "a retired harness is named at:\n" + "\n".join(hits)


def test_the_match_is_a_whole_word_and_ignores_case(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("it declined\nuse Retired here\n", encoding="utf-8")
    assert _hits(tmp_path, frozenset({"retired"}), ["a.md"]) == ["a.md:2"]
    assert _hits(tmp_path, frozenset({"line"}), ["a.md"]) == []


def test_changelogs_and_decisions_are_not_searched(tmp_path: Path) -> None:
    for path in ("CHANGELOG.md", "x/decisions/d.md"):
        file = tmp_path / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("retired\n", encoding="utf-8")
    assert _hits(tmp_path, frozenset({"retired"}), ["CHANGELOG.md", "x/decisions/d.md"]) == []
